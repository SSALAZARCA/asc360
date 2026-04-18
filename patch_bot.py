import re
import os

path = r"c:\proyectos IA\UM Colombia\Aplicación red de servicio\telegram-bot\bot\main.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Quitar nueva recepcion del check_cancel_intent para que no aborte silenciosamente
content = content.replace("ya no|nueva recepci[óo]n)\\b')", "ya no)\\b')")

# 2. Definir TEXT_FILTER antes de crear ConversationHandler
setup_block = '''TEXT_FILTER = filters.TEXT & ~filters.COMMAND & ~filters.Regex(r"(?i)^Nueva Recepci[óo]n$")

    conv_handler = ConversationHandler('''
if "TEXT_FILTER = " not in content:
    content = content.replace("conv_handler = ConversationHandler(", setup_block)

# 3. Aplicar TEXT_FILTER a los states (solo para aquellos que usaban TEXT & ~COMMAND)
content = content.replace("filters.TEXT & ~(filters.COMMAND)", "TEXT_FILTER")

# 4. Asegurarnos que entry_points sí use TEXT & ~COMMAND puro, ya que ahí SÍ necesitamos atrapar "Nueva Recepción"
entry_block_original = '''entry_points=[
            CommandHandler("start", start_command),
            MessageHandler(TEXT_FILTER, handle_general_text)
        ],'''
entry_block_fixed = '''entry_points=[
            CommandHandler("start", start_command),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_general_text)
        ],'''
content = content.replace(entry_block_original, entry_block_fixed)

# 5. Agregar el MessageHandler global de fallbacks para "Nueva Recepción" para que reinicie durante una conversación
fallback_original = '''fallbacks=[CommandHandler("cancelar", cancel_recepcion)]'''
fallback_fixed = '''fallbacks=[
            MessageHandler(filters.Regex(r"(?i)^Nueva Recepci[óo]n$"), handle_general_text),
            CommandHandler("cancelar", cancel_recepcion)
        ]'''
content = content.replace(fallback_original, fallback_fixed)

# Backup replacement just in case fallback_original was formatted differently
if fallback_fixed not in content:
    content = re.sub(
        r'fallbacks=\[\s*CommandHandler\("cancelar", cancel_recepcion\)\s*\]',
        fallback_fixed,
        content
    )

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print('Patch aplicado para Nueva Recepcion')
