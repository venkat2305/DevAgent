from langchain_google_genai import ChatGoogleGenerativeAI

# export GOOGLE_API_KEY="your_api_key_here"


def main():
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",  # or "gemini-1.5-flash", "gemini-1.5-pro"
        temperature=0.0,
    )

    response = llm.invoke("Say hi")
    print(response.content)


if __name__ == "__main__":
    main()
