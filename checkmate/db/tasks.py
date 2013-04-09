import pymongo
import mongodb

from celery import Celery

celery = Celery('tasks', broker='mongodb://checkmate:password@localhost:27017/checkmate')
driver = mongodb.Driver()
driver.database() # initialize MongoClient

@celery.task
def update(num):
    driver.save_deployment('84f9a07a718a465d9dff760f3dd07ffd',  {'id':'84f9a07a718a465d9dff760f3dd07ffd', "stuff":{"UPDATE":num}},
                           tenant_id=680640)

