from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return bool(request.user and request.user.is_authenticated and profile and profile.role in self.allowed_roles)


class IsWaiter(HasRole):
    allowed_roles = ("waiter",)


class IsDirector(HasRole):
    allowed_roles = ("director",)


class IsCashier(HasRole):
    allowed_roles = ("cashier",)


class IsDirectorOrCashier(HasRole):
    allowed_roles = ("director", "cashier")
