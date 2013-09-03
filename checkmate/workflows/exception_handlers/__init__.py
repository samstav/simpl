import logging

from checkmate.exceptions import CheckmateResetTaskTreeException
from exception_handler import ExceptionHandler
from reset_task_tree_exception_handler import ResetTaskTreeExceptionHandler

LOG = logging.getLogger(__name__)


def get_handlers(d_wf, failed_tasks_ids, context, driver):
    handlers = []

    for failed_task_id in failed_tasks_ids:
        try:
            failed_task = d_wf.get_task(failed_task_id)
            task_state = failed_task._get_internal_attribute("task_state")
            info = task_state["info"]
            exception = eval(info)

            if type(exception) is CheckmateResetTaskTreeException:
                handlers.append(ResetTaskTreeExceptionHandler(
                    d_wf, failed_task_id, context, driver))
        except Exception as exp:
            LOG.debug("ExceptionHandlerBase raised exception %s", str(exp))
    return handlers
