from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from articles import views

urlpatterns = [
    path("", views.index, name="index"),
    # Modelos disponibles
    path("api/models", views.get_models, name="get_models"),
    # Gestión de artículos
    path("api/articles", views.list_articles, name="list_articles"),
    path("api/articles/upload", views.upload_article, name="upload_article"),
    path("api/articles/<str:article_id>/tsne", views.get_article_tsne, name="get_article_tsne"),
    path("api/articles/<str:article_id>/ner", views.get_article_ner, name="get_article_ner"),
    path("api/articles/<str:article_id>/meta", views.get_article_meta, name="get_article_meta"),
    path("api/articles/<str:article_id>/cleaned-text", views.get_article_cleaned_text, name="get_article_cleaned_text"),
    path("api/articles/<str:article_id>/relations", views.article_relations, name="article_relations"),
    path("api/articles/<str:article_id>/reprocess", views.reprocess_article, name="reprocess_article"),
    # Workspaces
    path("api/workspaces", views.workspaces, name="workspaces"),
    path("api/workspaces/<str:workspace_id>", views.workspace_detail, name="workspace_detail"),
    path("api/workspaces/<str:workspace_id>/articles", views.workspace_articles, name="workspace_articles"),
    path("api/workspaces/<str:workspace_id>/process", views.workspace_process, name="workspace_process"),
    path("api/workspaces/<str:workspace_id>/aggregate", views.workspace_aggregate, name="workspace_aggregate"),
    path("api/workspaces/<str:workspace_id>/relations", views.workspace_relations, name="workspace_relations"),
    # Datos de ejemplo por modelo
    path("api/example/tsne", views.get_example_tsne, name="get_example_tsne"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=str(settings.BASE_DIR / "web"))
