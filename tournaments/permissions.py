from rest_framework import permissions

# Custom permission: allow safe methods for all, but only organizer can modify
class IsOrganizerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow the tournament organizer to edit/delete it.
    Assumes the model instance has an `organizer` attribute.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True
        # Write permissions only for the organizer
        return getattr(obj, 'organizer', None) == request.user