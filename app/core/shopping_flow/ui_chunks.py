from app.schemas.entities import A2UIChunk, CapturedData


def build_questionnaire_chunk(attr: dict, allow_multiple: bool = True) -> A2UIChunk:
    """Build question payload for FE questionnaire widget."""
    return A2UIChunk(
        a2ui={
            "type": "a2ui_questionnaire",
            "data": {
                "title": f"{attr['name']}",
                "allowMultiple": allow_multiple,
                "options": attr["options"],
                "attributeId": attr["id"],
            },
        }
    )


def build_interactive_product_chunk(product_data: dict) -> A2UIChunk:
    """Normalize product shape and emit card payload for swipe UI."""
    if isinstance(product_data, dict):
        product_model = CapturedData(**product_data)
    else:
        product_model = product_data

    return A2UIChunk(
        a2ui={
            "type": "a2ui_interactive_product",
            "data": {
                "product": product_model.model_dump(by_alias=True, exclude_none=True),
                "reasonsToReject": [
                    "Giá quá cao",
                    "Không hợp phong cách",
                    "Thương hiệu",
                    "Tính năng",
                    "Khác",
                ],
            },
        }
    )

