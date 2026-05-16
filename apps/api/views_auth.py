from django.contrib.auth.models import User
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.api.utils import ok, fail


class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not username or not password:
            return fail("username 和 password 不能为空", status_code=400)

        if User.objects.filter(username=username).exists():
            return fail("用户名已存在", status_code=400)

        user = User.objects.create_user(username=username, password=password)
        refresh = RefreshToken.for_user(user)
        return ok(
            {
                "user": {"id": user.id, "username": user.username},
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            message="注册成功",
            status_code=201,
        )


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not username or not password:
            return fail("username 和 password 不能为空", status_code=400)

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return fail("用户名或密码错误", status_code=401)

        if not user.check_password(password):
            return fail("用户名或密码错误", status_code=401)

        refresh = RefreshToken.for_user(user)
        return ok(
            {
                "user": {"id": user.id, "username": user.username},
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            message="登录成功",
        )


class ResetPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        new_password = request.data.get("new_password") or ""

        if not username or not new_password:
            return fail("username 和 new_password 不能为空", status_code=400)

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return fail("用户名不存在", status_code=404)

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return ok(message="密码重设成功")


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return ok({"id": user.id, "username": user.username})
