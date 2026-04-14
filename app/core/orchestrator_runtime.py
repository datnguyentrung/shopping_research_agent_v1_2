# app/core/orchestrator_runtime.py
import traceback
from collections.abc import AsyncIterator
from typing import Any

from app.agents import flow_orchestrator_agent
from app.agents.base_agent import interactive_agent, ranking_agent, \
    MODELS_TO_TRY  # Import agent gốc để can thiệp đổi model

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

        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        new_message = types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )

        max_attempts = len(MODELS_TO_TRY) + 1
        original_model = interactive_agent.model

        # --- LOGIC RETRY & FALLBACK MODEL ---
        for attempt in range(max_attempts):
            try:
                # Đổi model nếu đây là lần thử lại (fallback)
                if attempt > 0:
                    fallback_model = MODELS_TO_TRY[attempt - 1]
                    print(
                        f"\n[Runtime] ⚠️ Lỗi quá tải. Đang đổi sang model dự phòng: '{fallback_model}' (Lần thử {attempt + 1}/{max_attempts})")
                    interactive_agent.model = fallback_model

                # Tạo session mới mỗi lần thử để tránh rác bộ nhớ nếu lần trước bị sập giữa chừng
                session = await self._session_service.create_session(
                    app_name=APP_NAME,
                    user_id=DEFAULT_USER_ID,
                )

                if attempt == 0:
                    print(f"[Runtime] Bắt đầu tạo báo cáo với model: {interactive_agent.model} (Session: {session.id})")

                emitted = False
                async for event in self._runner.run_async(
                        user_id=DEFAULT_USER_ID,
                        session_id=session.id,
                        new_message=new_message,
                ):
                    text = self._extract_text(event)
                    if text:
                        emitted = True
                        yield text

                if not emitted:
                    print("[Runtime] No text emitted — using fallback reply")
                    yield self._fallback_reply(user_message)

                # Nếu chạy đến đây tức là stream mượt mà, không sinh lỗi -> Thoát vòng lặp
                break

            except Exception as exc:
                error_msg = str(exc)
                print(f"[Runtime] ❌ stream_text ERROR tại model '{interactive_agent.model}': {error_msg}")

                # Bắt chính xác lỗi 503 UNAVAILABLE của Google
                if "503" in error_msg and attempt < max_attempts - 1:
                    continue  # Bỏ qua lỗi, vòng lặp sẽ chạy tiếp và đổi model khác
                else:
                    # Nếu là lỗi khác không phải 503, hoặc đã hết sạch model dự phòng
                    traceback.print_exc()
                    yield "\n\n*Hệ thống hiện tại đang quá tải toàn bộ các kênh. Bạn vui lòng xem lại danh sách ở trên hoặc thử lại sau ít phút nhé!*"
                    break

            finally:
                # Đảm bảo LUÔN LUÔN trả lại model gốc cho hệ thống sau khi chạy xong
                # Để request của user tiếp theo vẫn được ưu tiên dùng model 3.1
                interactive_agent.model = original_model

    # async def generate_ranking_json(self, prompt: str) -> str:
    #     """
    #     Hàm này chuyên dùng để gọi RankingAgent.
    #     Không dùng stream, lấy kết quả một lần (Generate) để parse JSON.
    #     """
    #     try:
    #         from google.genai import types
    #
    #         # Gửi thẳng request vào ranking_agent
    #         response = await ranking_agent.generate_async(
    #             messages=[types.Content(role="user", parts=[types.Part(text=prompt)])]
    #         )
    #
    #         # Lấy text
    #         text_result = self._extract_text(response)
    #
    #         # Dọn dẹp rác markdown nếu LLM lỡ tay sinh ra
    #         text_result = text_result.replace("```json", "").replace("```", "").strip()
    #
    #         return text_result
    #     except Exception as e:
    #         print(f"[Runtime] ❌ Lỗi khi generate_ranking_json: {e}")
    #         return "[]"  # Trả về mảng rỗng để fallback

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
        return "\n\n*Hệ thống đang bảo trì một số tính năng sinh báo cáo, nhưng bạn vẫn có thể xem danh sách sản phẩm ở trên!*"


_flow_runtime_singleton = FlowOrchestratorRuntime()


def get_flow_runtime() -> FlowOrchestratorRuntime:
    return _flow_runtime_singleton