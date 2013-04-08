from tasks import update

def supah_test():
    update.delay(4)
    update.delay(6)
    update.delay(2)
    update.delay(3)
    update.delay(6)
    update.delay(9)
    update.delay(1)
    update.delay(100)
    update.delay(7)
