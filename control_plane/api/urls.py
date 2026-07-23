from django.urls import path

from .views import (
    CompositionCompileView,
    ArtifactDetailView,
    ArtifactListView,
    CompositionRunView,
    RegistryView,
    ScenarioCompileView,
    ScenarioFamilyDetailView,
    ScenarioFamilyListView,
    ScenarioRunDetailView,
    ScenarioRunListView,
    ScenarioRunView,
    SchemaView,
    SystemStatusView,
)

urlpatterns = [
    path("system/status", SystemStatusView.as_view(), name="system-status"),
    path("registry", RegistryView.as_view(), name="registry"),
    path("schemas/<str:schema_name>", SchemaView.as_view(), name="schema-detail"),
    path("scenario-families", ScenarioFamilyListView.as_view(), name="scenario-family-list"),
    path("scenario-families/<path:family_id>", ScenarioFamilyDetailView.as_view(), name="scenario-family-detail"),
    path("scenarios/compile", ScenarioCompileView.as_view(), name="scenario-compile"),
    path("scenarios/run", ScenarioRunView.as_view(), name="scenario-run"),
    path("compositions/compile", CompositionCompileView.as_view(), name="composition-compile"),
    path("compositions/run", CompositionRunView.as_view(), name="composition-run"),
    path("artifacts", ArtifactListView.as_view(), name="artifact-list"),
    path("artifacts/<str:artifact_id>", ArtifactDetailView.as_view(), name="artifact-detail"),
    path("runs", ScenarioRunListView.as_view(), name="run-list"),
    path("runs/<str:run_id>", ScenarioRunDetailView.as_view(), name="run-detail"),
]
