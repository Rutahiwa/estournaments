from django.shortcuts import render
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from .serializers import UserRegistrationSerializer, UserSerializer

class RegisterView(generics.CreateAPIView):
    """
    API endpoint for user registration
    Creates a new user and returns user data
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = (AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "user": UserSerializer(user).data,
            "message": "User created successfully",
        }, status=status.HTTP_201_CREATED)

class ProfileView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for retrieving and updating user profile
    Requires authentication
    """
    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user
