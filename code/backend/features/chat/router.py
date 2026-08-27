"""FastAPI router for Project-Scoped Multi-Session Chat."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status

from core.dependencies import get_chat_service
from features.chat.models import (
    ChatMessage,
    ChatMessagesResponse,
    ChatSessionListResponse,
    ChatSessionSummary,
    CreateChatRequest,
    SendMessageRequest,
    SendMessageResponse,
)
from features.chat.service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/chats", tags=["Project Chat"])


@router.get(
    "",
    response_model=ChatSessionListResponse,
    summary="List all chat sessions for a project",
)
async def list_project_chats(
    project_id: str,
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionListResponse:
    """List all chat sessions for a specific project, ordered by last update."""
    try:
        chats = await service.list_chats(project_id)
        return ChatSessionListResponse(chats=chats)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list chats for project %s", project_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list chats: {exc}",
        )


@router.post(
    "",
    response_model=ChatSessionSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session for a project",
)
async def create_project_chat(
    project_id: str,
    payload: CreateChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionSummary:
    """Create a new chat session for a project with optional custom title."""
    try:
        session = await service.create_chat(project_id, title=payload.title)
        return session
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create chat for project %s", project_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create chat: {exc}",
        )


@router.get(
    "/{chat_id}/messages",
    response_model=ChatMessagesResponse,
    summary="Get all messages for a specific chat session",
)
async def get_chat_messages(
    project_id: str,
    chat_id: str,
    service: ChatService = Depends(get_chat_service),
) -> ChatMessagesResponse:
    """Retrieve full conversation history including tool execution traces."""
    try:
        messages = await service.get_messages(project_id, chat_id)
        if messages is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session '{chat_id}' not found for project '{project_id}'",
            )
        return ChatMessagesResponse(messages=messages)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch messages for chat %s", chat_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {exc}",
        )


@router.post(
    "/{chat_id}/messages",
    response_model=SendMessageResponse,
    summary="Send a user message, run agent synthesis, and return response",
)
async def send_chat_message(
    project_id: str,
    chat_id: str,
    payload: SendMessageRequest,
    service: ChatService = Depends(get_chat_service),
) -> SendMessageResponse:
    """Send user message, execute agent with project context, return assistant response."""
    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message content cannot be empty or whitespace only",
        )
    try:
        result = await service.send_message(
            project_id=project_id,
            chat_id=chat_id,
            user_text=payload.message.strip(),
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session '{chat_id}' not found for project '{project_id}'",
            )
        user_msg, assistant_msg = result
        return SendMessageResponse(user_message=user_msg, assistant_message=assistant_msg)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to send message in chat %s", chat_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send message: {exc}",
        )


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a chat session",
)
async def delete_project_chat(
    project_id: str,
    chat_id: str,
    service: ChatService = Depends(get_chat_service),
) -> Dict[str, Any]:
    """Delete an existing chat thread."""
    try:
        deleted = await service.delete_chat(project_id, chat_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session '{chat_id}' not found",
            )
        return {
            "status": "success",
            "message": f"Chat session {chat_id} deleted",
            "chat_id": chat_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete chat %s", chat_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete chat: {exc}",
        )

