import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.core.mask_codec import build_mask_list_from_instance, get_mask_fields
from apps.core.models import QAR, QAR_Mask, QAR_PostProcess_Task
from apps.api.summary_service import rebuild_qar_summary

logger = logging.getLogger(__name__)

_UPLOAD_POST_PROCESS_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='qar-upload-post')
_RUNNING_QAR_IDS = set()
_RUNNING_LOCK = threading.Lock()

_DELETE_POST_PROCESS_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='qar-delete-post')
_RUNNING_DELETE_QAR_IDS = set()
_RUNNING_DELETE_LOCK = threading.Lock()

_DEFAULT_MAX_RETRIES = 2


def _build_mask_objects(qar_instances):
  mask_objects = []
  mask_fields = get_mask_fields()

  for qar in qar_instances:
    mask_data = {
      'qar_id': qar.qar_id,
      'dSimTime': qar.dSimTime,
      'mask_list': build_mask_list_from_instance(qar, mask_fields),
    }
    mask_objects.append(QAR_Mask(**mask_data))

  return mask_objects


def _upsert_mask_for_qar(qar_id, min_row_id=None, max_row_id=None):
  queryset = QAR.objects.filter(qar_id=qar_id).order_by('id')
  if min_row_id is not None:
    queryset = queryset.filter(id__gte=min_row_id)
  if max_row_id is not None:
    queryset = queryset.filter(id__lte=max_row_id)

  qar_instances = list(queryset)
  if not qar_instances:
    return

  existing_sim_times = set(
    QAR_Mask.objects.filter(qar_id=qar_id).values_list('dSimTime', flat=True)
  )
  target_instances = [item for item in qar_instances if item.dSimTime not in existing_sim_times]
  if not target_instances:
    return

  mask_objects = _build_mask_objects(target_instances)
  with transaction.atomic():
    if mask_objects:
      QAR_Mask.objects.bulk_create(mask_objects, batch_size=1000, ignore_conflicts=True)


def _mark_task_running(task_id, attempt_count):
  QAR_PostProcess_Task.objects.filter(id=task_id).update(
    status=QAR_PostProcess_Task.STATUS_RUNNING,
    attempt_count=attempt_count,
    started_time=timezone.now(),
    last_error='',
  )


def _mark_task_success(task_id):
  QAR_PostProcess_Task.objects.filter(id=task_id).update(
    status=QAR_PostProcess_Task.STATUS_SUCCESS,
    finished_time=timezone.now(),
    last_error='',
  )


def _mark_task_failed(task_id, error_message):
  QAR_PostProcess_Task.objects.filter(id=task_id).update(
    status=QAR_PostProcess_Task.STATUS_FAILED,
    finished_time=timezone.now(),
    last_error=str(error_message or '')[:2000],
  )


def _post_process_qar_data(qar_id, task_id, min_row_id=None, max_row_id=None):
  close_old_connections()
  try:
    logger.info('Start async post-processing for QAR ID: %s task_id=%s', qar_id, task_id)

    for attempt in range(1, _DEFAULT_MAX_RETRIES + 2):
      try:
        _mark_task_running(task_id, attempt)

        _upsert_mask_for_qar(qar_id, min_row_id=min_row_id, max_row_id=max_row_id)
        rebuild_qar_summary(qar_id)

        _mark_task_success(task_id)
        logger.info('Async post-processing completed for QAR ID: %s task_id=%s', qar_id, task_id)
        break
      except Exception as exc:
        logger.exception('Async post-processing failed for QAR ID: %s task_id=%s attempt=%s', qar_id, task_id, attempt)
        _mark_task_failed(task_id, exc)
        if attempt >= _DEFAULT_MAX_RETRIES + 1:
          break
  except Exception:
    logger.exception('Async post-processing outer failure for QAR ID: %s task_id=%s', qar_id, task_id)
    _mark_task_failed(task_id, 'outer worker failure')
  finally:
    with _RUNNING_LOCK:
      _RUNNING_QAR_IDS.discard(qar_id)
    close_old_connections()


def enqueue_qar_post_process(qar_id, min_row_id=None, max_row_id=None):
  normalized = str(qar_id or '').strip()
  if not normalized:
    return False

  with _RUNNING_LOCK:
    if normalized in _RUNNING_QAR_IDS:
      return False
    _RUNNING_QAR_IDS.add(normalized)

  task = QAR_PostProcess_Task.objects.create(
    qar_id=normalized,
    task_type=QAR_PostProcess_Task.TASK_TYPE_UPLOAD,
    status=QAR_PostProcess_Task.STATUS_PENDING,
    attempt_count=0,
    max_retries=_DEFAULT_MAX_RETRIES,
    mask_min_row_id=min_row_id,
    mask_max_row_id=max_row_id,
  )

  _UPLOAD_POST_PROCESS_POOL.submit(_post_process_qar_data, normalized, task.id, min_row_id, max_row_id)
  return True


def _post_delete_cleanup(qar_id, task_id):
  close_old_connections()
  try:
    logger.info('Start async delete cleanup for QAR ID: %s task_id=%s', qar_id, task_id)

    for attempt in range(1, _DEFAULT_MAX_RETRIES + 2):
      try:
        _mark_task_running(task_id, attempt)

        # Deletion already happened in request thread; only refresh summary here.
        rebuild_qar_summary(qar_id)

        _mark_task_success(task_id)
        logger.info('Async delete cleanup completed for QAR ID: %s task_id=%s', qar_id, task_id)
        break
      except Exception as exc:
        logger.exception('Async delete cleanup failed for QAR ID: %s task_id=%s attempt=%s', qar_id, task_id, attempt)
        _mark_task_failed(task_id, exc)
        if attempt >= _DEFAULT_MAX_RETRIES + 1:
          break

  except Exception:
    logger.exception('Async delete cleanup outer failure for QAR ID: %s task_id=%s', qar_id, task_id)
    _mark_task_failed(task_id, 'outer worker failure')
  finally:
    with _RUNNING_DELETE_LOCK:
      _RUNNING_DELETE_QAR_IDS.discard(qar_id)
    close_old_connections()


def enqueue_qar_delete_post_process(qar_id):
  normalized = str(qar_id or '').strip()
  if not normalized:
    return False

  with _RUNNING_DELETE_LOCK:
    if normalized in _RUNNING_DELETE_QAR_IDS:
      return False
    _RUNNING_DELETE_QAR_IDS.add(normalized)

  task = QAR_PostProcess_Task.objects.create(
    qar_id=normalized,
    task_type=QAR_PostProcess_Task.TASK_TYPE_DELETE,
    status=QAR_PostProcess_Task.STATUS_PENDING,
    attempt_count=0,
    max_retries=_DEFAULT_MAX_RETRIES,
  )

  _DELETE_POST_PROCESS_POOL.submit(_post_delete_cleanup, normalized, task.id)
  return True
