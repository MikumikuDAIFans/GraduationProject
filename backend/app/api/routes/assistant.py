"""Assistant routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.live_updates import broadcast_workspace_update
from app.api.deps import AssistantService, get_assistant_service, get_current_user_id
from app.api.schemas import (
    AssistantCurrentSessionRead,
    AssistantInboxRead,
    AssistantMessageCreate,
    AssistantResponse,
    AssistantSessionCreate,
    AssistantSessionListRead,
    AssistantSessionRead,
    AssistantSummaryRead,
    SpeechSynthesisRequest,
    VoiceAssistantResponse,
)
from app.input_adapters import WhisperInputAdapter
from app.output_adapters import GTTSOutputAdapter

router = APIRouter(prefix="/assistant", tags=["assistant"])
whisper_adapter = WhisperInputAdapter()
tts_adapter = GTTSOutputAdapter()


@router.post("/message", response_model=AssistantResponse)
async def send_message(
    payload: AssistantMessageCreate,
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantResponse:
    response = await service.send_message(user_id=user_id, payload=payload)
    await broadcast_workspace_update(user_id)
    return response


@router.post("/sessions", response_model=AssistantSessionRead)
async def create_session(
    payload: AssistantSessionCreate,
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantSessionRead:
    session = await service.create_session(user_id=user_id, payload=payload)
    await broadcast_workspace_update(user_id)
    return session


@router.get("/sessions", response_model=AssistantSessionListRead)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantSessionListRead:
    return await service.list_sessions(user_id=user_id, limit=limit)


@router.post("/voice", response_model=VoiceAssistantResponse)
async def send_voice_message(
    audio: UploadFile = File(...),
    session_id: int | None = Form(default=None),
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> VoiceAssistantResponse:
    audio_bytes = await audio.read()
    transcript = await whisper_adapter.process_input(audio_bytes)
    response = await service.send_message(
        user_id=user_id,
        payload=AssistantMessageCreate(session_id=session_id, message=transcript),
    )
    if isinstance(response, dict):
        return VoiceAssistantResponse.model_validate({**response, "transcript": transcript})
    return VoiceAssistantResponse(
        session_id=response.session_id,
        reply=response.reply,
        actions=response.actions,
        transcript=transcript,
    )


@router.post("/speak")
async def synthesize_speech(
    payload: SpeechSynthesisRequest,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    del user_id
    audio_bytes = await tts_adapter.synthesize(payload.text)
    return StreamingResponse(
        iter([audio_bytes]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'inline; filename="assistant-reply.mp3"'},
    )


@router.get("/sessions/{session_id}", response_model=AssistantSessionRead)
async def get_session(
    session_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantSessionRead:
    return await service.get_session(user_id=user_id, session_id=session_id)


@router.post("/sessions/{session_id}/archive")
async def archive_session(
    session_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> dict[str, bool]:
    result = await service.archive_session(user_id=user_id, session_id=session_id)
    await broadcast_workspace_update(user_id)
    return result


@router.delete("/sessions/{session_id}/messages")
async def clear_session_messages(
    session_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> dict[str, bool]:
    result = await service.clear_session_messages(user_id=user_id, session_id=session_id)
    await broadcast_workspace_update(user_id)
    return result


@router.get("/inbox", response_model=AssistantInboxRead)
async def get_inbox(
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantInboxRead:
    return await service.get_inbox(user_id=user_id)


@router.get("/current", response_model=AssistantCurrentSessionRead)
async def get_current_session(
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantCurrentSessionRead:
    return await service.get_current_session(user_id=user_id)


@router.get("/summary", response_model=AssistantSummaryRead)
async def get_summary(
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantSummaryRead:
    return await service.get_summary(user_id=user_id)


@router.post("/inbox/{item_id}", response_model=AssistantInboxRead)
async def update_inbox_item(
    item_id: str = Path(...),
    action: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    service: AssistantService = Depends(get_assistant_service),
) -> AssistantInboxRead:
    result = await service.mark_inbox_item(user_id=user_id, item_id=item_id, action=action)
    await broadcast_workspace_update(user_id)
    return result
