from app.celery_worker import celery_app
from app.service.interview_cheatsheet import get_interview_cheatsheet
from app.db.models import InterviewCheatSheetModel
from app.db.session import SessionLocal
from loguru import logger
import traceback
from app.db.session import get_db_session


@celery_app.task(name="generate_cheatsheet")
def generate_cheatsheet_task(resume_text, job_description, cheatsheet_type, pdf_filename, user_id):
    with get_db_session() as db:
        try:
            result = get_interview_cheatsheet(resume_text, job_description, cheatsheet_type)

            if result:
                cheatsheet_record = InterviewCheatSheetModel(
                    resume_text=resume_text,
                    job_description=job_description,
                    content=result,
                    user_id=user_id,
                    cheatsheet_type=cheatsheet_type,
                    filename=pdf_filename
                )
                db.add(cheatsheet_record)
                db.commit()
                db.refresh(cheatsheet_record)
                logger.info(f"Cheatsheet generated and saved for user {user_id}")
                return cheatsheet_record.id
            else:
                logger.warning("No content returned from cheatsheet generation.")
        except Exception as e:
            logger.error(f"Task failed: {e}")
            logger.debug(traceback.format_exc())
