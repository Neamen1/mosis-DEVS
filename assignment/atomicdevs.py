from pypdevs.DEVS import AtomicDEVS
from environment import *
import abc
import dataclasses

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
    
    def __init__(self, machine_names):
        # TODO: Initialize your router state
        pass

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
    def __init__(self, name, machine_names, routing_time_per_size=30.0):
        super().__init__(name)
        
        # Parameters
        self.machine_names = machine_names
        self.routing_time_per_size = routing_time_per_size  # Time per unit size (e.g., 30 seconds)
        
        # TODO: Define input ports
        # - from generator
        # - from each machine
        
        # TODO: Define output ports
        # - to each machine
        # - to sink
        
        # State
        self.state = RouterState(machine_names)
    
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
        # - Update machine availability information if machines notify you
        # - Update queue statistics when queue length changes
        # - Decide if you can dispatch a product
        pass
    
    def timeAdvance(self):
        # TODO: Return routing time (product.size × routing_time_per_size) if dispatching,
        # otherwise return inf when idle
        pass
    
    def outputFnc(self):
        # TODO: Output product to appropriate machine or sink
        pass
    
    def intTransition(self):
        # TODO: Update state after dispatching a product
        # - Update queue statistics when queue length changes
        pass
    
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
    def __init__(self, machine_names, routing_time_per_size=30.0):
        super().__init__("FIFORouter", machine_names, routing_time_per_size)
    
    def _selectProduct(self, waiting_products):
        # TODO: Implement FIFO selection (first product in the list)
        pass


class PriorityRouter(AbstractRouter):
    """
    Priority Router: Dispatches larger products before smaller products.
    """
    def __init__(self, machine_names, routing_time_per_size=30.0):
        super().__init__("PriorityRouter", machine_names, routing_time_per_size)
    
    def _selectProduct(self, waiting_products):
        # TODO: Implement priority selection (larger products first)
        pass


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
    
    def __init__(self, capacity):
        # TODO: Initialize your machine state
        # Note: Statistics are already initialized above
        pass
    
    def usedCapacity(self):
        """Calculate how much capacity is currently used."""
        # TODO: Sum up sizes of products in the machine
        pass


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
    def __init__(self, machine_id, capacity, max_wait_duration):
        super().__init__(f"Machine_{machine_id}")
        
        # Parameters
        self.machine_id = machine_id
        self.capacity = capacity
        self.max_wait_duration = max_wait_duration
        
        # State
        self.state = MachineState(capacity)
        
        # TODO: Define input ports (from router)
        
        # TODO: Define output ports (back to router, and to notify availability)
    
    def extTransition(self, inputs):
        # TODO: Implement external transition
        # - Handle incoming products from router
        # - Update remaining time if already waiting
        # - Decide when to start processing
        pass
    
    def timeAdvance(self):
        # TODO: Return appropriate time based on current mode
        pass
    
    def outputFnc(self):
        # TODO: Output processed products or availability notifications
        pass
    
    def intTransition(self):
        # TODO: Update state after processing or notifying. Also update statistics.
        pass
    
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
        
        return (utilization, avg_occupancy, self.state.num_batches)

