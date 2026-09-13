from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("start", views.start, name="start"),
    path("enter-demo", views.start, name="enter_demo"),
    path("sign-out", views.sign_out, name="sign_out"),
    path("leave-demo", views.sign_out),
    path("home", views.home, name="home"),
]
