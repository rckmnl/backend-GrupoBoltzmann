from firebase_admin import messaging
from typing import List, Union, Dict, Any
import logging

logger = logging.getLogger(__name__)

async def send_push_notification(
    tokens: Union[str, List[str]],
    title: str,
    body: str,
    data: Dict[str, Any] = None
):
    """
    Envía una notificación push DIRECTAMENTE mediante Firebase Cloud Messaging (V1).
    """
    if not tokens:
        return
    
    if isinstance(tokens, str):
        tokens = [tokens]
        
    tokens = [t for t in tokens if t]
    if not tokens:
        return

    string_data = {k: str(v) for k, v in (data or {}).items()}

    try:
        if len(tokens) == 1:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=string_data,
                token=tokens[0],
            )
            response = messaging.send(message)
            return {"success": True, "response": response}
        else:
            message = messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                data=string_data,
                tokens=tokens,
            )
            response = messaging.send_multicast(message)
            return {"success": True, "success_count": response.success_count}
    except Exception as e:
        logger.error(f"Error sending push notification via Firebase: {e}")
        return None
