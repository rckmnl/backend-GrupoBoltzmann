from firebase_admin import messaging
from typing import List, Union, Dict, Any
import logging
import requests

logger = logging.getLogger(__name__)

async def send_push_notification(
    tokens: Union[str, List[str]],
    title: str,
    body: str,
    data: Dict[str, Any] = None
):
    """
    Envía notificaciones push usando Expo Push Service (recomendado para Expo Go)
    o directamente mediante Firebase Cloud Messaging.
    """
    if not tokens:
        return
    
    if isinstance(tokens, str):
        tokens = [tokens]
        
    tokens = [t for t in tokens if t]
    if not tokens:
        return

    expo_tokens = [t for t in tokens if t.startswith("ExponentPushToken")]
    native_tokens = [t for t in tokens if not t.startswith("ExponentPushToken")]

    # 1. ENVIAR VIA EXPO
    if expo_tokens:
        try:
            print(f"[INFO] Enviando {len(expo_tokens)} notificaciones via Expo...")
            print(f"[DEBUG] Tokens: {expo_tokens}")
            expo_url = "https://exp.host/--/api/v2/push/send"
            messages = []
            for token in expo_tokens:
                msg_payload = {
                    "to": token,
                    "title": title,
                    "body": body,
                    "data": data or {},
                    "sound": "default"
                }
                messages.append(msg_payload)
            
            print(f"[DEBUG] Expo Payload: {messages}")
            response = requests.post(expo_url, json=messages, timeout=10)
            
            if response.status_code == 200:
                resp_json = response.json()
                print(f"[SUCCESS] Respuesta Expo: {resp_json}")
            else:
                print(f"[ERROR] Expo API error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[ERROR] Fallo crítico al enviar via Expo: {e}")

    # 2. ENVIAR VIA FIREBASE (Original)
    if native_tokens:
        string_data = {k: str(v) for k, v in (data or {}).items()}
        try:
            print(f"[INFO] Enviando {len(native_tokens)} notificaciones via Firebase...")
            if len(native_tokens) == 1:
                message = messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    data=string_data,
                    token=native_tokens[0],
                )
                response = messaging.send(message)
                return {"success": True, "response": response}
            else:
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(title=title, body=body),
                    data=string_data,
                    tokens=native_tokens,
                )
                response = messaging.send_each_for_multicast(message)
                return {"success": True, "success_count": response.success_count}
        except Exception as e:
            logger.error(f"Error sending push notification via Firebase: {e}")
            return None
