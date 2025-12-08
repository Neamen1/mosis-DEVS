from pypdevs.DEVS import AtomicDEVS
from environment import *
import abc
import dataclasses
from math import inf
from collections import deque 
import time

# ============================================================================
# IMPORTANT: PyPDEVS List Wrapping
# ============================================================================
# This version of PyPDEVS requires all outputs to be wrapped in lists.
# 
# When sending output:
#   return {self.out_port: [value]}  # Wrap in list
#
# When receiving input:
#   value = inputs[self.in_port]
#   if isinstance(value, list):      # Unwrap if needed
#       value = value[0]
#
# This applies to:
# - Products sent between components
# - Capacity notifications (integers) sent from Machines to Router
# ============================================================================

# ============================================================================
# Router: Dispatches products to machines based on their recipe
# ============================================================================

QUEUE = 0   
REMAINING_CAPACITY = 1
IS_AVAILABLE = 2
BATCH_TYPE = 3

@dataclasses.dataclass
class RouterState:
    """
    State of the Router.
    
    You will need to track:
    - Products waiting to be dispatched (queue/buffer)
    - Which machines are available (and their remaining capacities)
    - IMPORTANT: Which product_type each machine is currently batching (None if empty)
      * Machines can only process one product type at a time
      * When dispatching, only send products matching the machine's current batch type
      * Reset batch type when machine becomes empty (capacity = full capacity)
    - Routing time for the current product being dispatched
    - Any other information needed for your dispatching strategy
    """
    # Queue statistics tracking
    last_time: float = 0.0  # Time of last state change
    total_queue_area: float = 0.0  # Cumulative sum of (queue_length × time_duration)
    

    def __init__(self, machine_names, machine_capacities):
        # TODO: Initialize your router state

        self.machine_states = {}
        self.queue_length_general = 0
        self.product_to_dispatch = None
        self.current_routing_time = 0.0
        for name in machine_names:
            self.machine_states[name] = {
                QUEUE: deque(),        # products waiting for this machine
                REMAINING_CAPACITY: machine_capacities[name],
                IS_AVAILABLE: True,
                BATCH_TYPE: None
            }



class AbstractRouter(AtomicDEVS):
    """
    Abstract base class for routers.
    
    The router takes time to dispatch products, with larger products taking longer.
    Routing time = product.size × routing_time_per_size
    
    The Router receives products from:
    - Generator (new products entering the system)
    - Machines (products that have completed an operation)
    
    The Router sends products to:
    - Machines (for their next operation)
    - Sink (if all operations are complete)
    
    You need to define appropriate input/output ports and implement the DEVS functions.
    """
    def __init__(self, name, machine_names, machine_capacities, routing_time_per_size=30.0):
        super().__init__(name)
        
        # Parameters
        self.machine_names = machine_names
        self.machine_max_capacities = machine_capacities
        self.routing_time_per_size = routing_time_per_size  # Time per unit size (e.g., 30 seconds)
        # INPUT PORTS
        # - from generator
        self.generator_input = self.addInPort("generator_to_router")
        # - from each machine
        self.machine_inputs = {}
        for name in machine_names:
            self.machine_inputs[name] = self.addInPort(f"{name}_to_router")
        
        # OUTPUT PORTS
        # - to each machine
        self.machine_outputs = {}
        for name in machine_names:
            self.machine_outputs[name] = self.addOutPort(f"router_to_{name}")
        # - to sink
        self.sink_output = self.addOutPort("router_to_sink")
        
        self.init_time = time.time()   
        
        # State
        self.state = RouterState(machine_names, machine_capacities)
    
    def __repr__(self):
        return f"AbstractRouter(machine_states={self.state.machine_states} \n\
            averageQueueLength={self.getAverageQueueLength(self.state.last_time)})"

    def getQueueLength(self):
        """
        Get the current total queue length across all machines.
        
        Returns:
            Total number of products waiting to be dispatched
        """
        total_length = 0
        for machine_state in self.state.machine_states.values():
            total_length += len(machine_state[QUEUE])
        return total_length

    @abc.abstractmethod
    def _selectProduct(self, waiting_products):
        """
        Select which product to dispatch next from a list of waiting products.
        This method should be implemented by subclasses (FIFORouter, PriorityRouter).
        
        Args:
            waiting_products: List of products waiting for the same machine
        
        Returns:
            The selected product, or None if list is empty
        """
        pass
    
    def extTransition(self, inputs):
        # TODO: Implement external transition

        # - Handle products arriving from generator or machines
        # generator returns: {self.out_product: [self.state.next_product]}
        # machines return a capacity notification and a list of products like: [capacity(int), prod1, prod2...] (can be a notification without product)
        state = self.state

        def assignProductToMachine(product):
            # get next machine to dispatch to, if any, or send to sink if current_step >= len(recipe)
            if product.current_step < len(product.recipe):
                next_machine = product.recipe[product.current_step]
                state.machine_states[next_machine][QUEUE].append(product)
            else:
                # TODO: send to sink (make a list )
                pass
        
        queue_length_changed = False
        gen_in = inputs[self.generator_input][0]
        if(gen_in):
            assignProductToMachine(gen_in)
            state.queue_length_general += 1
            queue_length_changed = True
        
        
        # process inputs, filter products and capacity notifications
        # - Update machine availability information if machines notify you
        for machine, port in self.machine_inputs.items():
            has_notif = False
            if(isinstance(inputs[port][0], int)):
                has_notif = True

                current_capacity = inputs[port][0]
                if(current_capacity > state.machine_states[machine][REMAINING_CAPACITY]):       # more space appears (has remaining capacity). If remaining capacity decreases availability doesn't change
                    state.machine_states[machine][IS_AVAILABLE] = True
                    if(current_capacity == self.machine_max_capacities[machine]):               # machine is empty
                        state.machine_states[machine][BATCH_TYPE] = None
                elif(current_capacity==0):      # machine capacity 0 -> no more space or machine is closed
                    state.machine_states[machine][IS_AVAILABLE] = False
                
                state.machine_states[machine][REMAINING_CAPACITY] = current_capacity
                
                if(len(inputs[port]) < 2):  # no more data except notification
                    continue
            
            products = inputs[port][1:] if has_notif else inputs[port]
            for p in products:
                assignProductToMachine(p)
                state.queue_length_general += 1
                queue_length_changed = True


        # - Update queue statistics when queue length changes
        if(queue_length_changed):
            if(state.queue_length_general != self.getQueueLength()):
                raise ValueError("External queue length count is differrent from actual sum of all machines' queue length")
            
            curr_time = time.time() - self.init_time
            time_duration = curr_time - state.last_time
            state.total_queue_area += state.queue_length_general * time_duration
            state.last_time = curr_time


        # - Decide if you can dispatch a product
        if(state.queue_length_general > 0):
            for machine_name, machine_state in state.machine_states.items():
                if(machine_state[IS_AVAILABLE] and len(machine_state[QUEUE])>0):
                    # select product to dispatch
                    product_to_dispatch = self._selectProduct(machine_state[QUEUE])
                    if(product_to_dispatch is not None):
                        # set batch type if not set
                        if(machine_state[BATCH_TYPE] is None):
                            machine_state[BATCH_TYPE] = product_to_dispatch.product_type
                        # check if product matches batch type
                        elif(product_to_dispatch.product_type != machine_state[BATCH_TYPE]):
                            continue    # type mismatch, cannot dispatch this product now

                        if(product_to_dispatch.size > machine_state[REMAINING_CAPACITY]):
                            continue    # not enough capacity, cannot dispatch this product now

                        # set routing time (at this point product can fit in machine and matches batch type)
                        state.current_routing_time = product_to_dispatch.size * self.routing_time_per_size
                        
                        # store product to output in outputFnc and trigger timeAdvance
                        state.product_to_dispatch = (product_to_dispatch, machine_name)
                        break   # only dispatch one product at a time

        return state
    
    def timeAdvance(self):
        # TODO: Return routing time (product.size × routing_time_per_size) if dispatching,
        if self.state.product_to_dispatch is not None:
            return self.state.current_routing_time
        # otherwise return inf when idle
        return inf
    
    def outputFnc(self):
        # TODO: Output product to appropriate machine or sink
        if self.state.product_to_dispatch is not None:
            product, machine_name = self.state.product_to_dispatch
            # output to machine or sink
            if product.current_step < len(product.recipe):
                # send to machine
                return {self.machine_outputs[machine_name]: [product]}
            else:
                # send to sink
                return {self.sink_output: [product]}
        return {}
    
    def intTransition(self):
        # TODO: Update state after dispatching a product
        # - Update queue statistics when queue length changes
        state = self.state
        if(state.product_to_dispatch is not None):
            product, machine_name = state.product_to_dispatch

            # remove product from machine queue
            state.machine_states[machine_name][QUEUE].remove(product)

            # update remaining capacity
            state.machine_states[machine_name][REMAINING_CAPACITY] -= product.size

            # update availability
            if(state.machine_states[machine_name][REMAINING_CAPACITY] == 0):
                state.machine_states[machine_name][IS_AVAILABLE] = False

            # update product's current step
            product.current_step += 1

            # decrease general queue length
            state.queue_length_general -= 1

            # reset dispatched product and routing time
            state.product_to_dispatch = None
            state.current_routing_time = 0.0

            # update queue statistics
            curr_time = time.time() - self.init_time
            time_duration = curr_time - state.last_time
            state.total_queue_area += state.queue_length_general * time_duration
            state.last_time = curr_time

        return self.state
    
    def getAverageQueueLength(self, current_time):
        """
        Calculate the time-weighted average queue length.
        
        Args:
            current_time: The current simulation time
        
        Returns:
            The average queue length over the simulation period
        
        Note: You must update self.state.total_queue_area and self.state.last_time 
              in both extTransition and intTransition whenever the queue length changes.
              Formula: total_queue_area += queue_length * (current_time - last_time)
        """
        if current_time > 0:
            return self.state.total_queue_area / current_time
        return 0.0


class FIFORouter(AbstractRouter):
    """
    FIFO Router: Dispatches products in First-In-First-Out order.
    """
    def __init__(self, machine_names, machine_capacities, routing_time_per_size=30.0):
        super().__init__("FIFORouter", machine_names, machine_capacities, routing_time_per_size)
    
    def _selectProduct(self, waiting_products):
        # TODO: Implement FIFO selection (first product in the list)
        if len(waiting_products) == 0:
            return None
        return waiting_products[0]


class PriorityRouter(AbstractRouter):
    """
    Priority Router: Dispatches larger products before smaller products.
    """
    def __init__(self, machine_names, machine_capacities, routing_time_per_size=30.0):
        super().__init__("PriorityRouter", machine_names, machine_capacities, routing_time_per_size)
    
    def _selectProduct(self, waiting_products):
        # TODO: Implement priority selection (larger products first)
        if len(waiting_products) == 0:
            return None
        return max(waiting_products, key=lambda p: (p.current_step, p.size, -p.arrival_time))


# ============================================================================
# Machine: Processes products with batch capacity and max wait time
# ============================================================================

@dataclasses.dataclass
class MachineState:
    """
    State of a Machine.
    
    You will need to track:
    - Products currently in the machine
    - Current mode (e.g., waiting, processing, notifying)
    - Remaining time until processing starts/completes
    """
    # Statistics tracking
    total_processing_time: float = 0.0  # Total time spent processing
    total_occupancy_product: float = 0.0  # Sum of (capacity_used * processing_duration)
    num_batches: int = 0  # Number of batches processed
    
    def __init__(self):
        # TODO: Initialize your machine state
        # Note: Statistics are already initialized above
        self.products = []
        self.mode = "waiting"
        self.remaining_time = inf
        self.used_capacity = 0
    
    def getUsedCapacity(self):
        """Calculate how much capacity is currently used."""
        # Sum sizes of products in the machine
        used_capacity = 0
        for product in self.products:
            used_capacity += product.size
        return used_capacity


class Machine(AtomicDEVS):
    """
    Machine processes products in batches.
    
    Parameters:
        machine_id (str): Identifier for this machine (e.g., 'A', 'B')
        capacity (int): Maximum capacity of the machine
        max_wait_duration (float): Maximum time to wait before processing a non-full batch
    
    Behavior:
    - Accepts products from router (if capacity allows)
    - IMPORTANT: Can only batch products of the SAME product_type together
      * When receiving a product, validate it matches the existing batch type (if any)
      * Raise ValueError if different types are mixed (this catches Router bugs)
    - Waits for more products or until max_wait_duration expires
    - Processing duration comes from product.processing_times[machine_id]
      * All products in a batch have same type, so same processing time
    - Processes all products in batch
    - Sends processed products back to router
    
    You need to define appropriate input/output ports and implement the DEVS functions.
    """
    def __init__(self, machine_id, max_capacity, max_wait_duration):
        super().__init__(f"Machine_{machine_id}")
        
        # Parameters
        self.machine_id = machine_id
        self.max_capacity = max_capacity
        self.max_wait_duration = max_wait_duration
        self.init_time = time.time()
        # State
        self.state = MachineState()
        # Input port (from router)
        self.input_port = self.addInPort(f"router_to_{machine_id}")
        # Output port (back to router, and to notify availability)
        self.output_port = self.addOutPort(f"{machine_id}_to_router")
    
    def __repr__(self):
        utilization, avg_occupancy, num_batches = self.getStatistics(time.time() - self.init_time)
        return f"Machine(id={self.machine_id}, sim_time={time.time()-self.init_time}, used_capacity={self.state.used_capacity}/{self.max_capacity}, max_wait_duration={self.max_wait_duration},\
            stats=(utilization={utilization*100:.2f}%, avg_occupancy={avg_occupancy:.2f}, num_batches={num_batches}))"

    def extTransition(self, inputs):
        # TODO: Implement external transition
        # - Handle incoming products from router
        state = self.state
        incoming_products = inputs[self.input_port]
        changed_capacity = False
        for product in incoming_products:
            # Check if product can fit in machine
            if(state.used_capacity != state.getUsedCapacity()):
                raise ValueError(f"Machine {self.machine_id} used_capacity inconsistent with actual used capacity.")

            if(state.used_capacity + product.size > self.max_capacity):
                raise ValueError(f"Machine {self.machine_id} cannot accept product {product} due to capacity overflow.")
            
            if state.mode == "processing" or state.mode == "notifying":
                return state  # cannot accept products while processing or notifying. TODO: check if router will lose a product if it sends the product  
            
            # Check batch type consistency
            if len(state.products) > 0:
                existing_type = state.products[0].product_type
                if product.product_type != existing_type:
                    raise ValueError(f"Machine {self.machine_id} cannot accept product {product} of different type than existing batch type {existing_type}.")
            
            # Accept product
            if(state.used_capacity==0):
                state.remaining_time = self.max_wait_duration   # set wait timer when first product arrives
            state.products.append(product)
            state.used_capacity += product.size
            changed_capacity = True
            
        
        # - Update remaining time when already waiting
        # - Decide when to start processing
        if state.used_capacity > 0:
            state.remaining_time -= self.elapsed    # TODO: check if on processing it actually goes <= 0 so it can switch to notifiying in intTransition
        
        def start_processing():
            processing_time = state.products[0].processing_times[self.machine_id]
            state.remaining_time = processing_time
            state.mode = "processing"

        if state.mode == "waiting":
            if changed_capacity:
                if state.used_capacity == self.max_capacity:
                    start_processing()
            elif(state.used_capacity > 0):
                # check if max_wait_duration exceeded
                if state.remaining_time <= 0:
                    start_processing()

        return state
    
    def timeAdvance(self):
        # TODO: Return appropriate time based on current mode
        return self.state.remaining_time
    
    def outputFnc(self):
        # TODO: Output processed products or availability notifications
        state = self.state
        if state.mode == "notifying":
            # notify router of available capacity (after processing)
            available_capacity = self.max_capacity - state.used_capacity
            return {self.output_port: [available_capacity] + state.products}
        elif state.mode == "processing":
            return {self.output_port: [0]}  # notify no capacity while processing
        elif state.mode == "waiting":
            available_capacity = self.max_capacity - state.used_capacity
            return {self.output_port: [available_capacity]}  # notify available capacity while waiting
        return {}
    
    def intTransition(self):
        # TODO: Update state after processing or notifying. Also update statistics.
        state = self.state
        if state.mode == "processing":
            if state.remaining_time <= 0:
                # now can send products back to router
                # processing complete
                state.mode = "notifying"
                state.remaining_time = 0.0    # immediate notification
        elif state.mode == "notifying":
            # after notifying, write statistics
            state.num_batches += 1 
            state.total_processing_time += state.products[0].processing_times[self.machine_id]
            state.total_occupancy_product += state.used_capacity * state.products[0].processing_times[self.machine_id]

            # and go back to waiting
            state.products = []
            state.used_capacity = 0
            state.mode = "waiting"
            state.remaining_time = inf    # wait indefinitely for new products


        return state
    
    def getStatistics(self, simulation_time):
        """
        Get machine utilization statistics (pre-implemented for performance analysis).
        Returns: (utilization, avg_occupancy, num_batches)
        """
        if simulation_time > 0:
            utilization = self.state.total_processing_time / simulation_time
        else:
            utilization = 0.0
        
        if self.state.total_processing_time > 0:
            avg_occupancy = self.state.total_occupancy_product / self.state.total_processing_time
        else:
            avg_occupancy = 0.0
        
        return utilization, avg_occupancy, self.state.num_batches

