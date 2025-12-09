from pypdevs.DEVS import AtomicDEVS
from environment import *
import abc
import dataclasses
from math import inf
from collections import deque 
import time
from copy import deepcopy

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
        # Initialize your router state

        self.machine_states = {}
        self.to_sink = deque()
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
        total_length = len(self.state.to_sink)
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

        # - Handle products arriving from generator or machines
        # generator returns: {self.out_product: [self.state.next_product]}
        # machines return a capacity notification and a list of products like: [capacity(int), prod1, prod2...] (can be a notification without product)
        state = self.state
        
        queue_length_changed = False    # flag to decide if to update queue statistics

        def forwardProduct(product, state):
            # dispatch to next machine or sink queue
            if product.current_step < len(product.recipe):
                next_machine = product.recipe[product.current_step]
                state.machine_states[next_machine][QUEUE].append(product)
            else:
                state.to_sink.append(product)
            
            state.queue_length_general += 1
            
        if self.generator_input in inputs and inputs[self.generator_input]:
            gen_in = inputs[self.generator_input][0]
            forwardProduct(gen_in, state)
            queue_length_changed = True
        
        # process inputs, filter products and capacity notifications
        # - Update machine availability information if machines notify you
        for machine, port in self.machine_inputs.items():
            if port not in inputs or not inputs[port]:
                continue

            port_payload = inputs[port]
            has_notif = isinstance(port_payload[0], int)

            if has_notif:
                current_capacity = port_payload[0]
                
                # update availability based on capacity change
                prev_cap = state.machine_states[machine][REMAINING_CAPACITY]
                if current_capacity > prev_cap:
                    state.machine_states[machine][IS_AVAILABLE] = True
                    if current_capacity == self.machine_max_capacities[machine]:
                        state.machine_states[machine][BATCH_TYPE] = None
                elif(current_capacity==0):      # machine capacity 0 -> no more space or machine is closed
                    state.machine_states[machine][IS_AVAILABLE] = False
                
                state.machine_states[machine][REMAINING_CAPACITY] = current_capacity
                
                # if no products after notification, continue
                products = port_payload[1:] if len(port_payload) > 1 else []
            else:
                products = port_payload
            
            for p in products:
                forwardProduct(p, state)
                queue_length_changed = True


        # - Update queue statistics when queue length changes
        if(queue_length_changed):
            if(state.queue_length_general != self.getQueueLength()):
                raise ValueError("External queue length count is differrent from actual sum of all machines' queue length")
            
            # accumulate area and advance local last_time with self.elapsed
            # self.elapsed is the time since last transition (DEVS)
            state.total_queue_area += state.queue_length_general * self.elapsed
            state.last_time += self.elapsed


        # - Decide whether you can dispatch a product (only one dispatch at a time)
        if(state.queue_length_general > 0 and state.product_to_dispatch is None):

            for machine_name, machine_state in state.machine_states.items():
                if(machine_state[IS_AVAILABLE] and len(machine_state[QUEUE])>0):
                    # select product to dispatch
                    product_to_dispatch = self._selectProduct(machine_state[QUEUE])
                    
                    if product_to_dispatch is None:
                        continue

                    if len(product_to_dispatch.recipe) == product_to_dispatch.current_step:
                        state.product_to_dispatch = (product_to_dispatch, None)
                        state.current_routing_time = product_to_dispatch.size * self.routing_time_per_size
                        break
                    
                    # router-machines-states overhead:
                    # batch type logic
                    if(machine_state[BATCH_TYPE] is None):
                        machine_state[BATCH_TYPE] = product_to_dispatch.product_type
                    elif(product_to_dispatch.product_type != machine_state[BATCH_TYPE]):    # if product matches batch type
                        continue    # type mismatch, cannot dispatch        # TODO: choose another item with appropriate type (filtering?)

                    if(product_to_dispatch.size > machine_state[REMAINING_CAPACITY]):
                        continue    # not enough capacity, cannot dispatch  # TODO: choose another item with size machine_state[REMAINING_CAPACITY] or lower (filtering?)

                    # set routing time (at this point product can fit in machine and matches batch type)
                    state.current_routing_time = product_to_dispatch.size * self.routing_time_per_size
                    # store product to dispatch
                    state.product_to_dispatch = (product_to_dispatch, machine_name)
                    break   # dispatch only one product at a time

        return state
    
    def timeAdvance(self):
        # Return routing time (product.size × routing_time_per_size) if dispatching,
        if self.state.product_to_dispatch is not None:
            # routing time may be zero (immediate dispatch)
            return self.state.current_routing_time
        # otherwise return inf when idle
        return inf
    
    def outputFnc(self):
        # Output product to appropriate machine or sink
        if self.state.product_to_dispatch is None:
            return {}
        
        product, machine_name = self.state.product_to_dispatch
        if product.current_step < len(product.recipe):
            # send to machine
            return {self.machine_outputs[machine_name]: [product]}
        else:
            # send to sink
            return {self.sink_output: [product]}
        
    
    def intTransition(self):
        # Update state after dispatching a product
        # - Update queue statistics when queue length changes
        state = self.state

        if(state.product_to_dispatch is not None):
            product, machine_name = state.product_to_dispatch

            # if dispatched to machine, remove from that machine's queue and update capacity
            if machine_name is not None:
                # remove product from machine queue
                state.machine_states[machine_name][QUEUE].remove(product)

                # update remaining capacity and availability 
                state.machine_states[machine_name][REMAINING_CAPACITY] -= product.size
                if(state.machine_states[machine_name][REMAINING_CAPACITY] == 0):
                    state.machine_states[machine_name][IS_AVAILABLE] = False

                # update product's current step
                product.current_step += 1
            else:
                state.to_sink.remove(product)
            # decrease general queue length
            state.queue_length_general -= 1

            # update queue statistics
            state.total_queue_area += state.queue_length_general * state.current_routing_time
            state.last_time += state.current_routing_time
            
            # reset dispatched product and routing time 
            state.product_to_dispatch = None
            state.current_routing_time = 0.0    

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
        # FIFO selection (first product in the list)
        if len(self.state.to_sink)!=0:
            return self.state.to_sink[0]    # remove is done in intTransition 
        if(len(waiting_products) != 0):
            return waiting_products[0]
            
        return None


class PriorityRouter(AbstractRouter):
    """
    Priority Router: Dispatches larger products before smaller products.
    """
    def __init__(self, machine_names, machine_capacities, routing_time_per_size=30.0):
        super().__init__("PriorityRouter", machine_names, machine_capacities, routing_time_per_size)
    
    def _selectProduct(self, waiting_products):
        # priority selection (larger products first)
        if len(self.state.to_sink)!=0:
            return max(self.state.to_sink, key=lambda p: (p.size, -p.arrival_time))
        
        if len(waiting_products) == 0:
            return None
        
        return max(waiting_products , key=lambda p: (p.current_step, p.size, -p.arrival_time))


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
        # Initialize machine state
        # Note: Statistics are already initialized above
        self.products = []
        self.mode = "waiting"
        self.remaining_time = inf
        self.used_capacity = 0
        self.countdown_elapsed = None  # Accumulated elapsed time since first product arrived (None when idle)
    
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

        # State
        self.state = MachineState()
        # Input port (from router)
        self.input_port = self.addInPort(f"router_to_{machine_id}")
        # Output port (back to router, and to notify availability)
        self.output_port = self.addOutPort(f"{machine_id}_to_router")
    
    def __repr__(self):
        return f"Machine(id={self.machine_id}, used_capacity={self.state.used_capacity}/{self.max_capacity}, max_wait_duration={self.max_wait_duration})"

    def extTransition(self, inputs):
        # - Handle incoming products from router
        state = self.state
        # Decrement timers based on time since last transition (self.elapsed)
        elapsed = getattr(self, 'elapsed', 0.0)
        # If currently processing, decrement processing remaining time
        if state.mode == "processing" and state.remaining_time not in (inf, None):
            state.remaining_time -= elapsed
            if state.remaining_time < 0:
                state.remaining_time = 0.0
        # If waiting countdown active, accumulate elapsed time
        if state.countdown_elapsed is not None:
            state.countdown_elapsed += elapsed
            state.remaining_time = self.max_wait_duration - state.countdown_elapsed
            if state.remaining_time < 0:
                state.remaining_time = 0.0

        incoming_products = inputs[self.input_port]
        changed_capacity = False
        # process incoming products if any
        for product in incoming_products:
            # Check if product can fit in machine
            if(state.used_capacity != state.getUsedCapacity()):
                raise ValueError(f"Machine {self.machine_id} used_capacity inconsistent with actual used capacity.")

            if(state.used_capacity + product.size > self.max_capacity):
                raise ValueError(f"Machine {self.machine_id} cannot accept product {product} due to capacity overflow.")
            
            if state.mode == "processing":
                return state  # cannot accept products while processing. TODO: check if router will lose a product if it sends the product at processing
            
            # Check batch type consistency
            if len(state.products) > 0:
                existing_type = state.products[0].product_type
                if product.product_type != existing_type:
                    raise ValueError(f"Machine {self.machine_id} cannot accept product {product} of different type than existing batch type {existing_type}.")
            
            # Accept product
            if(state.used_capacity==0):
                # First product arrives - initialize countdown accumulator
                state.countdown_elapsed = 0.0
                state.remaining_time = self.max_wait_duration
            state.products.append(product)
            state.used_capacity += product.size
            changed_capacity = True

        # Decide when to start processing (after possible elapsed updates above)
        def start_processing(state):
            processing_time = state.products[0].processing_times[self.machine_id]
            state.remaining_time = processing_time
            state.mode = "processing"
            # reset countdown accumulator (no longer waiting)
            state.countdown_elapsed = None

        if state.mode == "waiting":
            if (state.used_capacity == 0):
                state.remaining_time = inf      # if empty wait indefinitely for next products
                return state

            if(state.remaining_time == 0):      # countdown expired -> start processing
                start_processing(state)
            elif changed_capacity:
                if state.used_capacity == self.max_capacity:
                    start_processing(state)

        return state
    
    def timeAdvance(self):
        # Return appropriate time based on current mode
        return self.state.remaining_time
    
    def outputFnc(self):
        # Output processed products or availability notifications
        state = self.state
        if state.mode == "processing":
            # processing completed -> output processed products (DEVS calls outputFnc at internal event)
            available_capacity = self.max_capacity
            # send available capacity (max after processing -> sending finished products out) plus processed products
            return {self.output_port: [available_capacity] + state.products}
        elif state.mode == "waiting":
            available_capacity = self.max_capacity - state.used_capacity
            return {self.output_port: [available_capacity]}  # notify available capacity while waiting (e.g after each product dispatch)
        return {}
    
    def intTransition(self):
        # Update state after processing or notifying. Also update statistics.
        state = self.state

        # Internal transition handling:
        # - If we were processing, the internal event corresponds to processing completion.
        #   DEVS calls outputFnc() first (which returns products), then intTransition() runs.
        if state.mode == "processing":
            # processing complete: update statistics and go back to waiting
            if len(state.products) > 0:
                processing_time = state.products[0].processing_times[self.machine_id]
            else:
                processing_time = 0.0

            state.num_batches += 1
            state.total_processing_time += processing_time
            state.total_occupancy_product += state.used_capacity * processing_time

            # clear batch and reset to waiting
            state.products = []
            state.used_capacity = 0
            state.countdown_elapsed = None
            state.mode = "waiting"
            state.remaining_time = inf    # wait indefinitely for new products

        # If we were waiting and reached countdown (internal event), start processing
        elif state.mode == "waiting":
            # internal event for waiting implies countdown expired -> start processing if any products present
            if state.used_capacity > 0:
                processing_time = state.products[0].processing_times[self.machine_id]
                state.remaining_time = processing_time
                state.mode = "processing"
                state.countdown_elapsed = None


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

