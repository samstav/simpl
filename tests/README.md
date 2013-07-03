## Our developer tests are divided into three categories: unit, functional, and integration.

There are many reasons for keeping tests well categorized, but these are some we value.

### Unit Tests
Even though all of the tests in this directory are written using unittest, there are tests that embody the term Unit Test. They have the following characteristics:

- They're fast! An individual unit test test case will likely run in a sub-millisecond timeframe on today's hardware. The entire Unit Test test suite (likely thousands of individual test cases) should run in less than 8 seconds. It's like a test rodeo!
- They're small. You won't see a lot of mocking (though there may be a very light, often hand-rolled mock or two) and you won't see a lot of setup or imports. The tests are concise and highly focused.
- They're cheap. There should be thousands of pure Unit Tests because they're so small and quick, making maintenance overhead nearly non-existent.

### Functional Tests
Functional tests build on the foundation established by Unit Tests. They couldn't care less about the external world: it's perfect as far as they are concerned. Functional Tests:

- Are fairly fast. An individual functional test test case will likely run in less than a tenth of a second, though occasionally a test case may push closer to a quarter-second run time.
- They take up a little space. You'll likely see more imports and generous use of mocking in functional tests. Since they test how different components in the system cooperate, they require a bit more setup.
- They're fairly cheap. Functional tests should stop short of I/O: disk access, network access and even in-memory database access should be avoided. Remember, these tests assume everything that isn't the project's code is infallable.

### Integration Tests
These tests don't take any of the silly shortcuts Unit Tests and Functional Tests take. They don't cheat! Integration Tests:

- Are more interested in being real than being fast! Thoroughness and assuming the worst of the world characterize Integration Tests. Therefore, how fast they run is a minor concern.
- They're fighting a tendency to be overweight. Just because they are thorough doesn't mean they can't be succinct. In a moment of honesty they might admit they're a little jealous of the other tests' speed and svelteness.
- This relationship is considered high-maintenance. Integration tests require much more time and attention and are more prone to breakdowns than their smaller cousins. Because of this cost, there should be far fewer Integration tests than the other two categories.

### How do I know where they go?
Use your best judgement. Most test cases will obviously fit one category. For those that don't, make your best guess with a slight preference for conservativism:

- If it's somewhere between Unit and Functional, the safe choice is Functional
- If it's somewhere between Functional and Integraion, the safe choice is Integration

### The Airplane Test

All developer tests should pass without a network connection. Integration tests that absolutely require a network connection should check for network connectivity before running and be skipped if no network is detected. This provides a high level of flexibility in development, since everything can be handled on the local (dev) machine. See `test_dns.py` for an example.

___Tests should never be placed in the root 'tests' folder. They should always be put in one of the subdirectories: unit, functional or integration.___

### Disabled Pylint Warnings

There are several pylint warnings that don't make sense in unit tests:

    - C0103: Invalid name (method names too long)
    - C0111: Missing docstring
    - R0903: Too few public methods
    - R0904: Too many public methods
    - W0212: Access to protected member of a client class
    - W0232: Class has no __init__ method

Because of this the line `# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232` should be at the top of each unit test file.


#### ___but most of all, ADD TESTS! Test Coverage == Goodness!___

