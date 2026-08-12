# i18n.py - Internationalization support
import json
import os
from typing import Dict, Optional
from structured_logging import get_logger

logger = get_logger("i18n")

class I18n:
    """Multi-language support"""
    
    SUPPORTED_LANGUAGES = ["en", "pt", "es", "fr"]
    DEFAULT_LANGUAGE = "pt"
    
    def __init__(self, translations_dir: str = "translations"):
        self.translations: Dict[str, Dict[str, str]] = {}
        self.current_language = self.DEFAULT_LANGUAGE
        self.load_translations(translations_dir)
    
    def load_translations(self, translations_dir: str):
        """Load translation files"""
        for lang in self.SUPPORTED_LANGUAGES:
            file_path = os.path.join(translations_dir, f"{lang}.json")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.translations[lang] = json.load(f)
                logger.info(f"Loaded translations for {lang}")
            except FileNotFoundError:
                logger.warning(f"Translation file not found for {lang}")
                self.translations[lang] = {}
    
    def set_language(self, language: str):
        """Set current language"""
        if language in self.SUPPORTED_LANGUAGES:
            self.current_language = language
        else:
            logger.warning(f"Unsupported language: {language}, using default")
            self.current_language = self.DEFAULT_LANGUAGE
    
    def t(self, key: str, language: Optional[str] = None, **kwargs) -> str:
        """Translate key"""
        lang = language or self.current_language
        
        # Get translation
        text = self.translations.get(lang, {}).get(key)
        
        if not text:
            # Fallback to English
            text = self.translations.get("en", {}).get(key)
        
        if not text:
            # Fallback to key itself
            text = key
            logger.warning(f"Missing translation for key: {key} in {lang}")
        
        # Replace variables
        try:
            if kwargs:
                text = text.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing variable in translation: {e}")
        
        return text
    
    def get_supported_languages(self):
        """Get list of supported languages"""
        return self.SUPPORTED_LANGUAGES

# Global i18n instance
_i18n = None

def init_i18n(translations_dir: str = "translations"):
    """Initialize i18n"""
    global _i18n
    _i18n = I18n(translations_dir)
    return _i18n

def get_i18n() -> I18n:
    """Get i18n instance"""
    global _i18n
    if not _i18n:
        _i18n = I18n()
    return _i18n

def t(key: str, language: Optional[str] = None, **kwargs) -> str:
    """Translate (shorthand)"""
    return get_i18n().t(key, language, **kwargs)

def set_language(language: str):
    """Set language (shorthand)"""
    get_i18n().set_language(language)

# Common UI strings
TRANSLATIONS = {
    "en": {
        "dashboard": "Dashboard",
        "customers": "Customers",
        "tickets": "Tickets",
        "deals": "Deals",
        "reports": "Reports",
        "settings": "Settings",
        "logout": "Logout",
        "add_new": "Add New",
        "edit": "Edit",
        "delete": "Delete",
        "save": "Save",
        "cancel": "Cancel",
        "search": "Search",
        "filter": "Filter",
        "export": "Export",
        "loading": "Loading...",
        "error": "Error",
        "success": "Success",
        "warning": "Warning",
        "no_data": "No data available",
        "welcome": "Welcome, {name}!",
        "logout_success": "You have been logged out",
        "invalid_credentials": "Invalid email or password",
        "unauthorized": "You don't have permission to access this resource",
        "not_found": "Resource not found",
        "server_error": "An error occurred on the server",
    },
    "pt": {
        "dashboard": "Painel",
        "customers": "Clientes",
        "tickets": "Tickets",
        "deals": "Negócios",
        "reports": "Relatórios",
        "settings": "Configurações",
        "logout": "Sair",
        "add_new": "Adicionar Novo",
        "edit": "Editar",
        "delete": "Deletar",
        "save": "Salvar",
        "cancel": "Cancelar",
        "search": "Pesquisar",
        "filter": "Filtrar",
        "export": "Exportar",
        "loading": "Carregando...",
        "error": "Erro",
        "success": "Sucesso",
        "warning": "Aviso",
        "no_data": "Nenhum dado disponível",
        "welcome": "Bem-vindo, {name}!",
        "logout_success": "Você foi desconectado",
        "invalid_credentials": "Email ou senha inválidos",
        "unauthorized": "Você não tem permissão para acessar este recurso",
        "not_found": "Recurso não encontrado",
        "server_error": "Ocorreu um erro no servidor",
    },
    "es": {
        "dashboard": "Panel",
        "customers": "Clientes",
        "tickets": "Tickets",
        "deals": "Ofertas",
        "reports": "Reportes",
        "settings": "Configuración",
        "logout": "Cerrar sesión",
        "add_new": "Añadir nuevo",
        "edit": "Editar",
        "delete": "Eliminar",
        "save": "Guardar",
        "cancel": "Cancelar",
        "search": "Buscar",
        "filter": "Filtrar",
        "export": "Exportar",
        "loading": "Cargando...",
        "error": "Error",
        "success": "Éxito",
        "warning": "Advertencia",
        "no_data": "Sin datos disponibles",
        "welcome": "¡Bienvenido, {name}!",
        "logout_success": "Has cerrado sesión",
        "invalid_credentials": "Email o contraseña inválidos",
        "unauthorized": "No tienes permiso para acceder a este recurso",
        "not_found": "Recurso no encontrado",
        "server_error": "Ocurrió un error en el servidor",
    },
    "fr": {
        "dashboard": "Tableau de bord",
        "customers": "Clients",
        "tickets": "Tickets",
        "deals": "Deals",
        "reports": "Rapports",
        "settings": "Paramètres",
        "logout": "Déconnexion",
        "add_new": "Ajouter nouveau",
        "edit": "Modifier",
        "delete": "Supprimer",
        "save": "Enregistrer",
        "cancel": "Annuler",
        "search": "Rechercher",
        "filter": "Filtrer",
        "export": "Exporter",
        "loading": "Chargement...",
        "error": "Erreur",
        "success": "Succès",
        "warning": "Avertissement",
        "no_data": "Aucune donnée disponible",
        "welcome": "Bienvenue, {name}!",
        "logout_success": "Vous avez été déconnecté",
        "invalid_credentials": "Email ou mot de passe invalide",
        "unauthorized": "Vous n'avez pas la permission d'accéder à cette ressource",
        "not_found": "Ressource non trouvée",
        "server_error": "Une erreur s'est produite sur le serveur",
    },
}
