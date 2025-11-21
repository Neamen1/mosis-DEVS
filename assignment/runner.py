#!/usr/bin/env python3
"""
Runner script for the Flexible Job Shop assignment.

This script runs simulations for all combinations of parameters and
generates CSV files and gnuplot scripts for visualization.
"""

import os
import sys

# Make sure we can import from the current directory
sys.path.insert(0, os.path.dirname(__file__))

from pypdevs.simulator import Simulator
from plot_template import make_plot_products_script, make_plot_box_script, make_plot_frequency_script
from system import *

## Parameters ##

target_num = 500  # Number of finished products required to terminate simulation

# How often to generate a product (on average)
gen_rate = 1/60/4  # once every 4 minutes

# Dispatching strategies
strategies = {
    # you can comment out one of these lines to reduce the number of experiments (useful for debugging):
    STRATEGY_FIFO: "fifo",
    STRATEGY_PRIORITY: "priority",
}

# System configurations
CONFIGURATIONS = {
    'baseline': {
        'machine_capacities': {'A': 3, 'B': 2},
        'gen_types': [
            (0, 1, ['A', 'B'], {'A': 15*60, 'B': 10*60}, 2/3),
            (1, 2, ['B', 'A'], {'A': 20*60, 'B': 13*60}, 1/3)
        ]
    },
    'add-new-machines': {
        'machine_capacities': {'A': 3, 'B': 2, 'A_new': 3, 'B_new': 2},
        'gen_types': [
            (0, 1, ['A', 'B'], {'A': 15*60, 'B': 10*60}, 2/3),
            (1, 2, ['B', 'A'], {'A': 20*60, 'B': 13*60}, 1/3)
        ]
    },
    'double-capacity': {
        'machine_capacities': {'A': 6, 'B': 4},
        'gen_types': [
            (0, 1, ['A', 'B'], {'A': 15*60, 'B': 10*60}, 2/3),
            (1, 2, ['B', 'A'], {'A': 20*60, 'B': 13*60}, 1/3)
        ]
    },
    'double-speed': {
        'machine_capacities': {'A': 3, 'B': 2},
        'gen_types': [
            (0, 1, ['A', 'B'], {'A': 7.5*60, 'B': 5*60}, 2/3),
            (1, 2, ['B', 'A'], {'A': 10*60, 'B': 6.5*60}, 1/3)
        ]
    }
}

# The different parameters to try for max_wait_duration
max_wait_durations = [0.0, 3.0*60, 6.0*60]  # 0, 3, 6 minutes (in seconds)
# max_wait_durations = [180.0]  # <-- uncomment if you only want to run an experiment with this value (useful for debugging)

outdir = "assignment_output"

plots_products = []
plots_box = []
plots_freq = []

os.makedirs(outdir, exist_ok=True)

# Try all combinations of configurations and strategies
for config_name, config in CONFIGURATIONS.items():
    for strategy_id, strategy_name in strategies.items():
        values = []
        # And in each experiment, try a bunch of different values for the 'max_wait_duration' parameter:
        for max_wait_duration in max_wait_durations:
            print(f"Run simulation: config={config_name}, strategy={strategy_name}, max_wait={max_wait_duration/60:.1f}min")
            
            sys_model = FlexibleJobShop(
                seed=0,
                target_num=target_num,
                gen_rate=gen_rate,
                gen_types=config['gen_types'],
                machine_capacities=config['machine_capacities'],
                dispatching_strategy=strategy_id,
                max_wait_duration=max_wait_duration,
            )
            
            sim = Simulator(sys_model)
            sim.setClassicDEVS()
            # sim.setVerbose()  # <-- uncomment to see what's going on
            sim.setTerminationCondition(lambda time, model: sys_model.sink.termination_condition())
            sim.simulate()
            
            # All the finished (non-spoiled) products that made it through
            finished_products = [p for p in sys_model.sink.state.products 
                                if not hasattr(p, 'is_spoiled') or not p.is_spoiled]
            values.append([product.flow_time for product in finished_products])
            
            # Print machine statistics
            # Use the router's last_time which tracks the actual time
            simulation_time = sys_model.router.state.last_time
            
            for machine_name, machine in sys_model.machines.items():
                utilization, avg_occupancy, num_batches = machine.getStatistics(simulation_time)
                print(f"  Machine {machine_name}: Utilization={utilization*100:.1f}%, Avg Occupancy={avg_occupancy:.2f}, Batches={num_batches}")
            
            # Print router queue statistics
            avg_queue_length = sys_model.router.getAverageQueueLength(simulation_time)
            print(f"  Router: Avg Queue Length={avg_queue_length:.2f}")
        
        # Write out all the product flow times for every 'max_wait_duration' parameter
        #  for every product, we write a line:
        #    <product_num>, time_max_wait0, time_max_wait1, time_max_wait2
        filename = f'{outdir}/output_{config_name}_{strategy_name}.csv'
        with open(filename, 'w') as f:
            try:
                for i in range(target_num):
                    f.write("%s" % i)
                    for j in range(len(values)):
                        # Convert to minutes for readability
                        f.write(", %5f" % (values[j][i] / 60.0))
                    f.write("\n")
            except IndexError as e:
                raise Exception(
                    "There was an IndexError, meaning that fewer finished products have made it to the sink than expected.\n"
                    "Your model is not (yet) correct."
                ) from e
        
        # Generate gnuplot code:
        for f, col in [
            (make_plot_products_script, plots_products),
            (make_plot_box_script, plots_box),
            (make_plot_frequency_script, plots_freq)
        ]:
            col.append(f(
                config=config_name,
                strategy=strategy_name,
                max_waits=[mwd/60 for mwd in max_wait_durations],  # Convert to minutes
                gen_num=target_num,
            ))

# Finally, write out a single gnuplot script that plots everything
with open(f'{outdir}/plot.gnuplot', 'w') as f:
    # First plot the products
    f.write('\n\n'.join(plots_products))
    # Then do the box plots
    f.write('\n\n'.join(plots_box))
    # Then the frequency plots
    f.write('\n\n'.join(plots_freq))

print("\n" + "="*80)
print(f"Results saved to {outdir}/")
print("To generate plots, run:")
print(f"  cd {outdir} && gnuplot plot.gnuplot")
print("="*80)
