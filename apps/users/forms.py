from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password

from apps.users.models import User
from apps.users.services import username_from_email


class SignupForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")
        if password and confirm and password != confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        if password:
            user = User(email=cleaned.get("email") or "", username="pending")
            validate_password(password, user)
        return cleaned

    def save(self) -> User:
        email = self.cleaned_data["email"]
        user = User.objects.create_user(
            username=username_from_email(email),
            email=email,
            password=self.cleaned_data["password"],
        )
        return user


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        email = (cleaned.get("email") or "").strip().lower()
        password = cleaned.get("password")
        if email and password:
            user = authenticate(self.request, username=email, password=password)
            if user is None:
                raise forms.ValidationError("Incorrect email or password.")
            self.user = user
        return cleaned
