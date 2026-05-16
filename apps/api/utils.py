from rest_framework.response import Response


def ok(data=None, message="ok", code=0, status_code=200):
    return Response({"code": code, "message": message, "data": data}, status=status_code)


def fail(message="error", code=1, data=None, status_code=400):
    return Response({"code": code, "message": message, "data": data}, status=status_code)
