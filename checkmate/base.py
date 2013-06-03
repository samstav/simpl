'''
Base Class
'''
from checkmate import utils


class Manager(object):
    '''Handles interface between API and database'''

    def __init__(self, drivers):
        self.driver = drivers.get('default')
        self.simulator_driver = drivers.get('simulation')

    def select_driver(self, api_id):
        '''Returns appropriate driver based on whether this is a simulation or
        not
        '''
        if utils.is_simulation(api_id):
            return self.simulator_driver
        else:
            return self.driver
