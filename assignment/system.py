from pypdevs.DEVS import CoupledDEVS
from atomicdevs import *

STRATEGY_FIFO = 0
STRATEGY_PRIORITY = 1

class FlexibleJobShop(CoupledDEVS):
    """
    The complete flexible job shop system.
    
    Parameters:
        seed (int): Random seed for generator
        target_num (int): Number of finished products required to terminate simulation
        gen_rate (float): Product generation rate (products/second)
        gen_types (list of tuples): Product types as (product_type, size, recipe, processing_times, probability)
        machine_capacities (dict): Capacity for each machine, e.g., {'A': 3, 'B': 2}
        dispatching_strategy (int): STRATEGY_FIFO or STRATEGY_PRIORITY
        max_wait_duration (float): Maximum wait time for all machines
        routing_time_per_size (float): Time to route a product per unit size
    """
    def __init__(self,
        seed=0,
        target_num=500,
        gen_rate=1.0/60.0/4.0,  # once every 4 minutes
        gen_types=[(0, 1, ['A', 'B'], {'A': 15*60, 'B': 10*60}, 2/3), (1, 2, ['B', 'A'], {'A': 20*60, 'B': 13*60}, 1/3)],
        machine_capacities={'A': 3, 'B': 2},
        dispatching_strategy=STRATEGY_FIFO,
        max_wait_duration=60.0*3.0,  # 3 minutes
        routing_time_per_size=30.0  # 30 seconds per unit size
    ):
        super().__init__("FlexibleJobShop")
        
        # Create generator (provided) - generates infinitely
        generator = self.addSubModel(Generator(
            seed=seed,
            lambd=gen_rate,
            gen_types=gen_types,
        ))
        
        # TODO: Create router based on dispatching strategy
        # Pass routing_time_per_size to the router constructor
        if dispatching_strategy == STRATEGY_FIFO:
            router = None  # TODO: Create FIFORouter
        elif dispatching_strategy == STRATEGY_PRIORITY:
            router = None  # TODO: Create PriorityRouter
        
        # TODO: Create machines based on machine_capacities
        # Note: Processing times come from the products themselves, not from machine parameters
        machines = {}  # TODO: Dictionary mapping machine_id to Machine instance
        
        # Create sink (provided) - terminates when target_num finished products received
        sink = self.addSubModel(Sink(target_num=target_num))
        
        # TODO: Connect the components
        # - Generator -> Router
        # - Router -> Machines
        # - Machines -> Router
        # - Router -> Sink
        
        # Store references for later access
        self.generator = generator
        self.sink = sink
        self.machines = machines  # Store machines dict for statistics

