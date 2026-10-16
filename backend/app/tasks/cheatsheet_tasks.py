from app.celery_worker import celery_app
from app.service.interview_cheatsheet import get_interview_cheatsheet
from app.db.models import InterviewCheatSheetModel
from loguru import logger
from app.db.session import get_db_session


@celery_app.task(name="generate_cheatsheet")
def generate_cheatsheet_task(resume_text, job_description, cheatsheet_type, pdf_filename, user_id):
    result = get_interview_cheatsheet(resume_text, job_description, cheatsheet_type)
    if not result:
        logger.warning("No content returned from cheatsheet generation.")
        raise RuntimeError("Cheatsheet generation returned no content.")

    with get_db_session() as db:
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

        return {
            "id": cheatsheet_record.id,
            "user_id": user_id,
            "cheatsheet_type": cheatsheet_type,
            "content": result,
            "generated_at": cheatsheet_record.generated_at.isoformat(),
            "filename": pdf_filename,
        }
