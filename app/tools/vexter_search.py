from fastapi import HTTPException
from google.cloud import discoveryengine

from app.core.config.init_clients import PROJECT_ID, ENGINE_ID, bootstrap_api_env
from app.schemas.requests import SearchRequest
import asyncio


async def perform_search(request: SearchRequest):
    try:
        bootstrap_api_env()
        client = discoveryengine.SearchServiceClient()
        serving_config = client.serving_config_path(
            project=PROJECT_ID,
            location="global",
            data_store=ENGINE_ID,
            serving_config="default_search",
        )

        exact_match_keyword = f'"{request.keyword}"'

        search_filter = ""
        if request.category_filter:
            search_filter = f'category: ANY("{request.category_filter}")'

        search_req = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=exact_match_keyword,
            filter=search_filter if search_filter else None,
            page_size=10,
        )

        response = client.search(search_req)

        results_list = []
        for result in response.results:
            struct_data = result.document.struct_data
            results_list.append(
                {
                    "id": result.document.id,
                    "title": struct_data.get("title", "Khong co tieu de"),
                    "link": struct_data.get("link", ""),
                }
            )

        # print(f"Search results for '{request.keyword}': {len(results_list)} items found.")
        # print(results_list)

        return {"status": "success", "data": results_list}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    test_request = SearchRequest(keyword="ao khoac bomber nam chinh hang", category_filter="Ao khoac")
    search_results = asyncio.run(perform_search(test_request))
    print(search_results)