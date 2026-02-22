from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from articles import views


urlpatterns = [
    path("", views.index, name="index"),
    path("api/articles", views.list_articles, name="list_articles"),
    path("api/articles/upload", views.upload_article, name="upload_article"),
    path("api/articles/<str:article_id>/tsne", views.get_article_tsne, name="get_article_tsne"),
    path("api/articles/<str:article_id>/ner", views.get_article_ner, name="get_article_ner"),
    path("api/articles/<str:article_id>/meta", views.get_article_meta, name="get_article_meta"),
    path("api/articles/<str:article_id>/cleaned-text", views.get_article_cleaned_text, name="get_article_cleaned_text"),
    path("api/example/tsne", views.get_example_tsne, name="get_example_tsne"),
]

urlpatterns += static(settings.STATIC_URL, document_root=str(settings.BASE_DIR / "web"))
