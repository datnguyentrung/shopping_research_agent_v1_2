# app/core/orchestrator_runtime.py
import traceback
from collections.abc import AsyncIterator
from typing import Any

from app.agents import flow_orchestrator_agent

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

APP_NAME = "shopping_agent"
DEFAULT_USER_ID = "default_user"


class FlowOrchestratorRuntime:

    def __init__(self, agent: Any | None = None):
        self._agent = agent or flow_orchestrator_agent
        self._runner = None
        self._session_service = None
        self._init_runner()

    def _init_runner(self):
        """Khởi tạo Runner — bắt lỗi import rõ ràng."""
        try:
            self._session_service = InMemorySessionService()
            self._runner = Runner(
                agent=self._agent,
                app_name=APP_NAME,
                session_service=self._session_service,
            )
            print("[Runtime] ✅ ADK Runner initialized OK")
        except Exception as exc:
            print(f"[Runtime] ❌ Runner init FAILED: {exc!r}")
            traceback.print_exc()

    async def stream_text(self, user_message: str) -> AsyncIterator[str]:
        if self._runner is None:
            print("[Runtime] Runner is None — returning fallback")
            yield self._fallback_reply(user_message)
            return

        try:
            from google.adk.sessions import InMemorySessionService
            from google.genai import types

            session = await self._session_service.create_session(
                app_name=APP_NAME,
                user_id=DEFAULT_USER_ID,
            )
            print(f"[Runtime] Session created: {session.id}")

            new_message = types.Content(
                role="user",
                parts=[types.Part(text=user_message)],
            )

            emitted = False
            async for event in self._runner.run_async(
                user_id=DEFAULT_USER_ID,
                session_id=session.id,
                new_message=new_message,
            ):
                print(f"[Runtime] Event received: {type(event).__name__}, is_final={event.is_final_response()}")

                if not event.is_final_response():
                    continue

                text = self._extract_text(event)
                print(f"[Runtime] Extracted text: {repr(text[:80]) if text else 'EMPTY'}")

                if text:
                    emitted = True
                    yield text

            if not emitted:
                print("[Runtime] No text emitted — using fallback")
                yield self._fallback_reply(user_message)

        except Exception as exc:
            print(f"[Runtime] ❌ stream_text ERROR: {exc!r}")
            traceback.print_exc()
            yield self._fallback_reply(user_message)

    @staticmethod
    def _extract_text(event: Any) -> str:
        try:
            if event.content and event.content.parts:
                return "".join(
                    part.text
                    for part in event.content.parts
                    if hasattr(part, "text") and part.text
                )
        except AttributeError:
            pass
        return ""

    @staticmethod
    def _fallback_reply(user_message: str) -> str:
        return f"Bạn vừa hỏi: {user_message}. Tôi sẽ tiếp tục hỗ trợ bạn."


_flow_runtime_singleton = FlowOrchestratorRuntime()


def get_flow_runtime() -> FlowOrchestratorRuntime:
    return _flow_runtime_singleton