from app.core.config import Settings


def test_comma_separated_allowed_types_are_parsed():
    settings = Settings(
        allowed_image_types="image/jpeg,image/png,image/webp",
        _env_file=None,
    )
    assert settings.allowed_image_types == [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]
