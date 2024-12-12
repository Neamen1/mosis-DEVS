from pypdevs.DEVS import AtomicDEVS
from job import Job
import random

# Define the state of the generator as a structured object
class GeneratorState:
    def __init__(self, gen_num, seed=0):
        # Current simulation time (statistics)
        self.current_time = 0.0
        # Remaining time until generation of new event
        self.remaining = 0.0
        # Counter on how many events to generate still
        self.to_generate = gen_num
        # Next job to output
        self.next_job = None
        # State of our random number generator
        self.random = random.Random(seed)

class Generator(AtomicDEVS):
    def __init__(self, gen_param, size_param, gen_num):
        AtomicDEVS.__init__(self, "Generator")
        # Output port for the event
        self.out_event = self.addOutPort("out_event")

        # Parameters defining the generator's behaviour
        self.gen_param = gen_param
        self.size_param = size_param

        # Init state
        self.state = GeneratorState(gen_num)
        self.__nextJob() # already schedule the first job to generate

    def __nextJob(self):
        # Determine size of the event to generate
        size = max(1, int(self.state.random.gauss(self.size_param, 5)))
        # Calculate current time (note the addition!)
        creation = self.state.current_time + self.state.remaining
        # Update state
        self.state.next_job = Job(size, creation)
        self.state.remaining = self.state.random.expovariate(self.gen_param)

    def intTransition(self):
        # Update simulation time
        self.state.current_time += self.timeAdvance()
        # Update number of generated events
        self.state.to_generate -= 1
        if self.state.to_generate == 0:
            # Already generated enough events, so stop
            self.state.remaining = float('inf')
            self.state.next_job = None
        else:
            # Still have to generate events, so sample for new duration
            self.__nextJob()
        return self.state

    def timeAdvance(self):
        # Return remaining time; infinity when generated enough
        return self.state.remaining

    def outputFnc(self):
        # Output the new event on the output port
        return {self.out_event: self.state.next_job}
