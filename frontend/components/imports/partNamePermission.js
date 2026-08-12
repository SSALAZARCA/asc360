// Shared copy for the part-name/description superadmin-only edit gate
// (sdd/parts-description-source-of-truth design D8-D10). Keep this string in
// sync with `assert_name_editor`'s 403 detail in
// backend/app/services/parts_description_service.py -- the backend is the
// real enforcement point, this is only the UI-facing explanation shown when
// a non-superadmin's name/description cell renders read-only.
export const SUPERADMIN_ONLY_NAME_EDIT_MESSAGE = 'Solo superadmin puede editar el nombre del repuesto';
