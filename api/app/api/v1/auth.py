from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token
from app.models.all_models import User
from app.schemas.user import UserRegister, UserLogin, Token, UserOut, ForgotPasswordRequest, ResetPasswordRequest
from app.services.auth_service import get_current_user
from app.services.activity_service import log_activity

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    role_str = user_in.role.value if hasattr(user_in.role, 'value') else str(user_in.role)

    user = User(
        name=user_in.name,
        email=user_in.email,
        password_hash=hash_password(user_in.password),
        role=role_str,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(
        db=db,
        user_id=user.id,
        action=f"User registered as {user.role}",
        entity_type="USER",
        entity_id=user.id,
    )

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.post("/login", response_model=Token)
def login(login_in: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_in.email).first()
    if not user or not verify_password(login_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is deactivated. Please contact your Team Lead.",
        )

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user account found with this email address."
        )
    return {
        "message": "Account verified. You may now reset your password.",
        "email": user.email,
        "name": user.name,
        "role": user.role
    }


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user account found with this email address."
        )

    user.password_hash = hash_password(req.new_password)
    db.commit()

    log_activity(
        db=db,
        user_id=user.id,
        action="Password was reset successfully",
        entity_type="USER",
        entity_id=user.id,
    )

    return {"message": "Password updated successfully. You can now log in with your new password."}

