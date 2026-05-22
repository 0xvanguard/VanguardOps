from app.services.rules import CATEGORY_ROUTING, DEFAULT_ROUTING

class AssignmentService:
    @staticmethod
    def get_initial_assignment(category: str) -> str:
        """Determina a quién asignar el ticket inicialmente"""
        if not category:
            return DEFAULT_ROUTING
        return CATEGORY_ROUTING.get(category.lower(), DEFAULT_ROUTING)

assignment_service = AssignmentService()
