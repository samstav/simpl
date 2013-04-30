def run_with_params(args):
    '''Helper method that handles command line arguments:

    Having command line parameters passed on to checkmate is handy
    for troubleshooting issues. This helper method encapsulates
    this logic so it can be used in any test.

    '''
    import unittest2 as unittest

    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)

