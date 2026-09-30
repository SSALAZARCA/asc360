"""Small built-in denylist of very common passwords (compared in lowercase).

Only entries that could pass the length/letter/digit rules matter, but the
shorter ones are kept so the list stays a plain reference of what is common.
"""

COMMON_PASSWORDS = frozenset({
    "1234567890", "12345678910", "0987654321", "0123456789", "1234567891",
    "qwertyuiop", "qwertyuiop1", "qwerty12345", "qwerty123456", "asdfghjkl1",
    "asdfghjklñ", "zxcvbnm123", "1q2w3e4r5t", "1qaz2wsx3edc", "q1w2e3r4t5",
    "abcdefghij", "abc1234567", "abcd123456", "a1b2c3d4e5", "aaaaaaaa11",
    "password1", "password12", "password123", "password1234", "password12345",
    "passw0rd12", "passw0rd123", "p@ssw0rd12", "p@ssword123", "pa55word12",
    "contraseña1", "contraseña12", "contraseña123", "contraseña1234",
    "contrasena1", "contrasena12", "contrasena123", "contrasena1234",
    "clave12345", "clave123456", "clave2026", "clave20261", "clave2025",
    "motored123", "motored1234", "motored12345", "motored2024", "motored2025",
    "motored2026", "motored2027", "motored.123", "motored#123", "motored*123",
    "hero123456", "hero12345", "hero1234567", "hero2026", "hero202612",
    "eshero123", "eshero1234", "eshero2026", "hmcl123456", "hmcl2026",
    "colombia123", "colombia1234", "colombia2026", "colombia12345",
    "bienvenido1", "bienvenido123", "bienvenida123", "bienvenido2026",
    "admin12345", "admin123456", "admin1234567", "administrador1", "admin2026",
    "usuario123", "usuario1234", "usuario12345", "motos12345", "moto123456",
    "iloveyou12", "iloveyou123", "welcome123", "welcome1234", "letmein123",
    "changeme123", "changeme12", "temporal123", "temporal1234", "cambiame123",
    "santiago123", "sebastian123", "alejandro123", "daniel12345", "nicolas123",
    "medellin123", "bogota12345", "bogota2026", "cali1234567", "barranquilla1",
    "123456789a", "a123456789", "1234567abc", "12345678aa", "123123123a",
    "futbol12345", "nacional123", "millonarios1", "america1234", "junior12345",
})
