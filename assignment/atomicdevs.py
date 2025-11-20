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
    - Products waiting to be dispatched (buffer)
    - Which machines are available (and their remaining capacities)
    - Any other information needed for your dispatching strategy
    """
    def __init__(self, machine_names):
        # TODO: Initialize your router state
        pass

class AbstractRouter(AtomicDEVS):
    """
    Abstract base class for routers.
    
    The Router receives products from:
    - Generator (new products entering the system)
    - Machines (products that have completed an operation)
    
    The Router sends products to:
    - Machines (for their next operation)
    - Sink (if all operations are complete)
    
    You need to define appropriate input/output ports and implement the DEVS functions.
    """
    def __init__(self, name, machine_names):
        super().__init__(name)
        
        # TODO: Define input ports
        # - from generator
        # - from each machine
        
        # TODO: Define output ports
        # - to each machine
        # - to sink
        
        # State
        self.state = RouterState(machine_names)
        
        # Parameters
        self.machine_names = machine_names
    
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
        # - Decide if you can dispatch a product
        pass
    
    def timeAdvance(self):
        # TODO: Return 0 if you have products to dispatch, inf otherwise
        pass
    
    def outputFnc(self):
        # TODO: Output product to appropriate machine or sink
        pass
    
    def intTransition(self):
        # TODO: Update state after dispatching a product
        pass


class FIFORouter(AbstractRouter):
    """
    FIFO Router: Dispatches products in First-In-First-Out order.
    """
    def __init__(self, machine_names):
        super().__init__("FIFORouter", machine_names)
    
    def _selectProduct(self, waiting_products):
        # TODO: Implement FIFO selection (first product in the list)
        pass


class PriorityRouter(AbstractRouter):
    """
    Priority Router: Dispatches larger products before smaller products.
    """
    def __init__(self, machine_names):
        super().__init__("PriorityRouter", machine_names)
    
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
    def __init__(self, capacity):
        # TODO: Initialize your machine state
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
        processing_duration (float): Time to process a batch
        max_wait_duration (float): Maximum time to wait before processing a non-full batch
    
    Behavior:
    - Accepts products from router (if capacity allows)
    - Waits for more products or until max_wait_duration expires
    - Processes all products in batch
    - Sends processed products back to router
    
    You need to define appropriate input/output ports and implement the DEVS functions.
    """
    def __init__(self, machine_id, capacity, processing_duration, max_wait_duration):
        super().__init__(f"Machine_{machine_id}")
        
        # Parameters
        self.machine_id = machine_id
        self.capacity = capacity
        self.processing_duration = processing_duration
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
        # TODO: Update state after processing or notifying
        pass

