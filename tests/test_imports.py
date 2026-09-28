"""Tests to verify all modules import correctly."""


class TestImports:
    """Verify all modules can be imported without errors."""

    def test_import_config(self):
        """Config module imports."""
        from src.config import (
            CONFIG,
            get_db_config,
            get_storage_config,
            get_thumbnails_config,
            get_vault_url,
            load_config,
        )

        assert callable(load_config)
        assert callable(get_db_config)
        assert callable(get_storage_config)
        assert callable(get_thumbnails_config)
        assert callable(get_vault_url)
        assert isinstance(CONFIG, dict)

    def test_import_database(self):
        """Database module imports."""
        from src.database import (
            close_db,
            get_db,
            init_db,
        )

        assert callable(init_db)
        assert callable(close_db)
        assert callable(get_db)

    def test_import_models(self):
        """Models module imports all classes."""
        from src.models import (
            Album,
            MediaItem,
        )

        assert MediaItem is not None
        assert Album is not None

    def test_import_storage_protocol(self):
        """Storage protocol imports."""
        from src.modules.storage.protocol import StorageBackend

        assert StorageBackend is not None

    def test_import_storage_nas(self):
        """NAS storage imports."""
        from src.modules.storage.nas import NASStorage

        assert NASStorage is not None

    def test_import_storage_dropbox(self):
        """Dropbox storage imports."""
        from src.modules.storage.dropbox_backend import DropboxStorage

        assert DropboxStorage is not None

    def test_import_storage_registry(self):
        """Storage registry imports."""
        from src.modules.storage.registry import (
            get_backend,
            get_default,
            init_backends,
        )

        assert callable(init_backends)
        assert callable(get_backend)
        assert callable(get_default)

    def test_import_catalog_service(self):
        """Catalog service imports."""
        from src.modules.catalog.service import (
            create_media,
            get_media,
        )

        assert callable(create_media)
        assert callable(get_media)

    def test_import_catalog_metadata(self):
        """Catalog metadata imports."""
        from src.modules.catalog.metadata import (
            extract_image_metadata,
        )

        assert callable(extract_image_metadata)

    def test_import_catalog_routes(self):
        """Catalog routes import."""
        from src.modules.catalog.routes import router

        assert router is not None

    def test_import_files_routes(self):
        """Files routes import."""
        from src.modules.catalog.files_routes import router

        assert router is not None

    def test_import_search_service(self):
        """Search service imports."""
        from src.modules.search.service import list_all_media, search

        assert callable(search)
        assert callable(list_all_media)

    def test_import_albums_service(self):
        """Albums service imports."""
        from src.modules.albums.service import (
            create_album,
        )

        assert callable(create_album)

    def test_import_albums_routes(self):
        """Albums routes import."""
        from src.modules.albums.routes import router

        assert router is not None

    def test_import_integrations_service(self):
        """Integrations service imports."""
        from src.modules.integrations.service import import_paper_figures

        assert callable(import_paper_figures)

    def test_import_integrations_routes(self):
        """Integrations routes import."""
        from src.modules.integrations.routes import router

        assert router is not None

    def test_import_sources_service(self):
        """Sources service imports."""
        from src.modules.sources.service import create_source

        assert callable(create_source)

    def test_import_scanner_service(self):
        """Scanner service imports."""
        from src.modules.scanner.service import scan_source

        assert callable(scan_source)

    def test_import_tagger_service(self):
        """Tagger service imports."""
        from src.modules.tagger.service import suggest_tags

        assert callable(suggest_tags)

    def test_import_thumbnails_service(self):
        """Thumbnails service imports."""
        from src.modules.thumbnails.service import generate_image_thumbnail

        assert callable(generate_image_thumbnail)

    def test_import_dropbox_service(self):
        """Dropbox service imports."""
        from src.modules.dropbox.service import upload_file

        assert callable(upload_file)

    def test_import_main_app(self):
        """Main app imports."""
        from src.main import app

        assert app is not None
        assert app.title == "Media Library"
