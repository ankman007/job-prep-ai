from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from app.db.models import InterviewCheatSheetModel
from app.db.session import get_db
from app.routes.auth import get_current_user

router = APIRouter()

@router.get('/details')
async def get_user_details(
    current_user=Depends(get_current_user)
):
    try:
        return {
            "status": "success",
            "message": "User details fetched successfully.",
            "user_details": {
                "username": current_user.name,
                "email": current_user.email,
                "location": current_user.location,
                "id": current_user.id,
                "bio": current_user.bio,
                "job_title": current_user.job_title  
            }
        }
    except Exception as e:
        logger.exception(f"Error fetching user details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user details."
        )


@router.get('/cheatsheets', response_model=dict, status_code=status.HTTP_200_OK)
async def get_user_cheatsheets(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:
        user_cheatsheets = db.query(InterviewCheatSheetModel).filter_by(user_id=current_user.id).all()

        if not user_cheatsheets:
            return {
                "status": "success",
                "message": "No cheatsheets found for the user.",
                "cheatsheets": []
            }

        formatted_cheatsheets = []
        for sheet in user_cheatsheets:
            try:
                formatted_cheatsheets.append({
                    "id": sheet.id,
                    "user_id": sheet.user_id,
                    "cheatsheet_type": sheet.cheatsheet_type,
                    "content": sheet.content,
                    "filename": sheet.filename,
                    "generated_at": sheet.generated_at
                })
            except Exception as e:
                logger.exception(f"Error parsing content for sheet id {sheet.id}: {e}")
                continue  
        return {
            "status": "success",
            "message": "Fetched user cheatsheets successfully.",
            "cheatsheets": formatted_cheatsheets
        }

    except Exception as e:
        logger.exception(f"Error fetching cheatsheets: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user cheatsheets."
        )
