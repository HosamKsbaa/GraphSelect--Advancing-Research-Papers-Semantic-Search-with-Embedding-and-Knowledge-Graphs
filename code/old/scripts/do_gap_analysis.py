import asyncio
import httpx

async def main():
    project_id = "bf4f1d61-eabb-4f96-92a0-37a288fe644f"
    base_url = "http://localhost:8002/api"
    
    async with httpx.AsyncClient() as client:
        # 1. Get coverage
        print("Fetching coverage analysis...")
        resp = await client.get(f"{base_url}/analysis/{project_id}/coverage")
        if resp.status_code == 200:
            data = resp.json()
            for cov in data.get("coverages", []):
                print(f"\nQuestion: {cov['question_text']}")
                print(f"Status: {cov['status'].upper()} (Score: {cov['coverage_score']})")
                print(f"Covered by {cov['paper_count']} papers")
                
                # If it's a gap, suggest queries
                if cov['status'] == 'gap':
                    print("--> Generating gap queries...")
                    q_resp = await client.post(
                        f"{base_url}/analysis/{project_id}/gap-queries",
                        json={"gap_question": cov['question_text'], "max_queries": 3},
                        timeout=60.0
                    )
                    if q_resp.status_code == 200:
                        q_data = q_resp.json()
                        for q in q_data.get("queries", []):
                            print(f"    - {q}")
                    else:
                        print("    Failed to generate queries:", q_resp.text)
        else:
            print("Failed to get coverage:", resp.text)

if __name__ == "__main__":
    asyncio.run(main())
