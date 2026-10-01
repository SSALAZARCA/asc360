/**
 * frontend/components/motored/actionIcons.js
 *
 * Single action -> icon map for Motored row actions, so the same action
 * always shows the same icon on every screen.
 */
import {
  Pencil, Ban, RotateCcw, XCircle, Check, X, KeyRound, Download, Eye, Play,
  Save, Undo2, MapPin, EyeOff, PlusCircle, Link2, Unlink, Unlock,
  Lock, LockOpen, FileSpreadsheet, Send, Scissors, RefreshCw, GitCompareArrows,
  FlaskConical, History,
} from 'lucide-react';

export const ACTION_ICONS = {
  Editar: Pencil,
  Desactivar: Ban,
  Reactivar: RotateCcw,
  Anular: XCircle,
  Aprobar: Check,
  Rechazar: X,
  'Cambiar contraseña': KeyRound,
  Descargar: Download,
  'Ver detalle': Eye,
  Aplicar: Play,
  Guardar: Save,
  Cancelar: Undo2,
  Mapear: MapPin,
  Ignorar: EyeOff,
  'Crear como OTROS': PlusCircle,
  'Vincular Telegram': Link2,
  'Desvincular Telegram': Unlink,
  Desbloquear: Unlock,
  // Pedidos (Fase 4)
  Cerrar: Lock,
  Reabrir: LockOpen,
  Exportar: FileSpreadsheet,
  'Marcar como enviado': Send,
  'Aplicar recorte': Scissors,
  'Recalcular fallidas': RefreshCw,
  Comparar: GitCompareArrows,
  'Nuevo escenario': FlaskConical,
  Historial: History,
};
