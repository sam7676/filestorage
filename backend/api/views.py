from django.contrib.auth.models import User
from rest_framework.authentication import (
    BaseAuthentication,
)
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import AccessToken
from PIL import Image
import random
from collections import defaultdict
from api.views_extension import (
    upload_image,
    upload_video,
    TagConditions,
    delete_items,
    get_items_and_paths_from_tags,
    TAG_STYLE_OPTIONS,
)
from api.models import FileState, FileType
from django.http import FileResponse
from api.utils.overrides import override_random_item


class CookieTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        token = response.data.get("access")
        refresh = response.data.get("refresh")

        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="Strict",
            max_age=3600,
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh,
            httponly=True,
            secure=True,
            samesite="Strict",
            max_age=7 * 24 * 3600,
        )
        return response


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        try:
            refresh_token = request.COOKIES.get("refresh_token")

            request.data["refresh"] = refresh_token

            response = super().post(request, *args, **kwargs)
            new_access = response.data.get("access")

            # Set the new access token in an HttpOnly cookie
            response.set_cookie(
                key="access_token",
                value=new_access,
                httponly=True,
                secure=True,
                samesite="Strict",
                max_age=3600,  # 1 hour
            )
            return response

        except Exception as e:
            print(e)
            raise e


class CookieTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = request.COOKIES.get("access_token")
        if not token:
            return None  # No token found, skip authentication
        try:
            access_token = AccessToken(token)
            user_id = access_token["user_id"]
            user = User.objects.get(id=user_id)
            return (user, None)
        except Exception as e:
            print(type(e))
            raise AuthenticationFailed("Invalid or expired token")


class CheckIsAuthenticated(APIView):
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"Authentic token received!"})


class FileUpload(APIView):
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            data = request.FILES

            possible_image = data.get("image", None)
            possible_video = data.get("video", None)

            if possible_image is not None:
                upload_image(Image.open(possible_image))

            if possible_video is not None:
                upload_video(possible_video)

            return Response({"message": "Files successfully uploaded!"})

        except Exception as e:
            print(e)
            raise e


class RandomItem(APIView):
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            filetype = request.data.get("type")

            tags_data = request.data.get("tags")

            tags = defaultdict(list)

            for tag in tags_data:
                name = tag["name"].strip().lower()
                condition = tag["condition"]
                value = tag["value"].strip().lower()

                if condition not in TAG_STYLE_OPTIONS:
                    raise Exception("Condition not recognised")

                tags[(name, condition)].append(value)

            tags[("state", TagConditions.Is.value)] += [
                int(FileState.NeedsLabel),
                int(FileState.NeedsTags),
                int(FileState.NeedsClip),
                int(FileState.Complete),
            ]

            tags = override_random_item(tags, filetype)

            for k, v in tags.items():
                # Gathering distinct
                v = list(set(v))
                tags[k] = v

            for k, v in list(tags.items()):
                # With the keyword all we remove all conditions for that tag
                if "all" in v:
                    tags.pop(k)
                # On the "play" keyword we start auto-queueing images
                elif k[0] == "play":
                    tags.pop(k)

            items = get_items_and_paths_from_tags(tags)

            keys = list(items.keys())

            random_id = random.choice(keys)

            item_info = items[random_id]

            path = item_info["path"]
            mime_type = item_info["mime_type"]

            # Open the file as a stream
            file_handle = open(path, "rb")

            response = FileResponse(file_handle, content_type=mime_type)
            # Add metadata to headers (must be strings)
            response["X-Item-ID"] = str(random_id)
            response["X-Label"] = item_info["label"]
            response["X-Width"] = str(item_info["width"])
            response["X-Height"] = str(item_info["height"])
            response["X-Media-Type"] = (
                "image" if item_info["filetype"] == int(FileType.Image) else "video"
            )

            return response

        except Exception as e:
            print(e)
            raise e


class DeleteItem(APIView):
    authentication_classes = [CookieTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            item_id = request.data.get("item_id")
            delete_items({item_id})

            return Response({"message": "Item successfully deleted"})

        except Exception as e:
            print(e)
            raise e
