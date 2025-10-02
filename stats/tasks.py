import logging

from celery import shared_task
from django.db import transaction, OperationalError

# from faceai.views import process_face_recognition  # Temporarily disabled
from .models import ActivityInterval
from .s3handler import S3Handler

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 5}
)
def verify_headshot_task(self, interval_id, headshot_index):
    """
    Verify a headshot using AI model and update its status.

    Args:
        interval_id (int): ID of the ActivityInterval
        headshot_index (int): Index of the headshot in the interval's headshots list
    """
    try:
        with transaction.atomic(using='default', savepoint=False):
            try:
                # Get the interval with select_for_update and nowait
                interval = ActivityInterval.objects.select_for_update(nowait=True).get(id=interval_id)
            except OperationalError as e:
                if 'database is locked' in str(e):
                    # Retry with exponential backoff if database is locked
                    raise self.retry(exc=e, countdown=self.request.retries * 5 + 1)
                raise

            # Validate headshot index
            if headshot_index >= len(interval.headshots):
                return

            # Get the headshot data
            headshot = interval.headshots[headshot_index]
            image_url = headshot.get('url')

            if not image_url:
                return

            try:
                # Call AI verification service
                verification_result = run_ai_verification(image_url, interval_id)

                # Update headshot status
                headshot.update({
                    'status': verification_result['status'],
                    'confidence_score': verification_result.get('confidence_score', 0),
                    'verified_by': 'system'
                })

                interval.headshots[headshot_index] = headshot
                interval.verification_status = calculate_interval_status(interval.headshots)
                interval.save(update_fields=['headshots', 'verification_status'])

            except Exception as e:
                raise self.retry(exc=e)

    except ActivityInterval.DoesNotExist:
        pass
    except OperationalError as e:
        if 'database is locked' in str(e):
            raise self.retry(exc=e, countdown=self.request.retries * 5 + 1)
        raise
    except Exception as e:
        raise self.retry(exc=e)


def run_ai_verification(image_url, interval_id):
    """
    Run AI verification on the headshot.
    """
    try:
        # Get image bytes from S3
        s3_handler = S3Handler()
        image_bytes = s3_handler.get_image_bytes(image_url)

        # Get employee name from interval
        interval = ActivityInterval.objects.get(id=interval_id)
        employee_name = interval.employee.user.name

        # Get the verification result using process_face_recognition
        result = process_face_recognition(image_bytes, employee_name)

        # Map status based on result
        # If result status is error, mark as SUSPICIOUS otherwise VERIFIED
        status = 'SUSPICIOUS' if result.get('status') == 'error' else 'VERIFIED'

        return {
            'status': status,
            'confidence_score': 0
        }

    except Exception as e:
        return {
            'status': 'SUSPICIOUS',
            'confidence_score': 0
        }


def calculate_interval_status(headshots):
    """
    Calculate overall interval verification status based on headshots.
    Only uses VERIFIED, SUSPICIOUS, and PENDING states.
    """
    if not headshots:
        return 'PENDING'

    status_counts = {
        'VERIFIED': 0,
        'SUSPICIOUS': 0,
        'PENDING': 0
    }

    for headshot in headshots:
        status = headshot.get('status', 'PENDING')
        status_counts[status] = status_counts.get(status, 0) + 1

    # If any headshot is suspicious, mark interval as suspicious
    if status_counts['SUSPICIOUS'] > 0:
        return 'SUSPICIOUS'

    # If all headshots are verified, mark as verified
    if status_counts['PENDING'] == 0:
        return 'VERIFIED'

    # Otherwise, keep as pending
    return 'PENDING'
