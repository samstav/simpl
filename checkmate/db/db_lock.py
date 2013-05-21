class DbLock(object):
    def __init__(self, driver, key, timeout):
        self.key = key
        self.timeout = timeout
        self.driver = driver
        self()

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        self.driver.release_lock(self.key)

    def __call__(self):
        self.driver.acquire_lock(self.key, self.timeout)
