import streamlit as st
from backend import generate_blog

st.set_page_config(page_title="Agentic AI Blog Generator",page_icon="🤖",layout="wide")

st.markdown("""
<style>

.stApp{

    background:#0E1117;

}


.block-container{

    max-width:1280px;

    padding-top:3rem;

    padding-bottom:3rem;

}

/* Remove top black header */

header{

    background:transparent !important;

}

[data-testid="stHeader"]{

    background:transparent;

}

[data-testid="stToolbar"]{

    right:1rem;

}


section[data-testid="stSidebar"]{

    background:#1B1F2A;

    border-right:1px solid #2E3446;

}

section[data-testid="stSidebar"] h1{

    font-size:34px;

    font-weight:700;

}

section[data-testid="stSidebar"] textarea{

    border-radius:15px;

}

section[data-testid="stSidebar"] button{

    height:52px;

    border-radius:14px;

    font-size:18px;

    font-weight:600;

}


.hero{

    background:linear-gradient(
        135deg,
        #2563EB,
        #4F46E5,
        #7C3AED
    );

    border-radius:22px;

    padding:45px;

    color:white;

    box-shadow:
    0px 15px 35px rgba(0,0,0,.25);

    margin-bottom:35px;

}

.hero h1{

    font-size:58px;

    margin-bottom:10px;

}

.hero h4{

    color:#E5E7EB;

    line-height:1.6;

}

.badge{

    display:inline-block;

    background:rgba(255,255,255,.15);

    padding:10px 18px;

    border-radius:50px;

    margin-right:10px;

    margin-top:12px;

    font-weight:600;

}


[data-testid="stVerticalBlockBorderWrapper"]{

    border-radius:18px;

}


[data-testid="metric-container"]{

    background:#1B2230;

    border:1px solid #2E3446;

    border-radius:16px;

    padding:18px;

}

.stButton>button{

    background:#2563EB;

    border:none;

    color:white;

}

.stButton>button:hover{

    background:#1D4ED8;

}


.stDownloadButton>button{

    border-radius:12px;

}

.footer{

    text-align:center;

    color:#8B949E;

    margin-top:60px;

}

</style>
""",unsafe_allow_html=True)

if "blog" not in st.session_state:
    st.session_state.blog=""

with st.sidebar:
    st.markdown(
        """
        # ⚙️ Blog Settings
        Configure your blog generation request.
        """
    )

    st.divider()

    topic = st.text_area(
        "📝 Blog Topic",
        placeholder="""Examples:

    • State of AI Model Evaluation
    • LangGraph Tutorial
    • Future of AI Agents
    • Delta Lake Architecture
    • Retrieval Augmented Generation
    """,
        height=200,
    )

    st.caption(f"Characters: {len(topic)}")

    st.divider()

    generate = st.button(
        "🚀 Generate Blog",
        use_container_width=True,
        type="primary",
    )

    st.divider()

    st.markdown("### 💡 Example Topics")

    examples = [
        "State of AI Model Evaluation",
        "LangGraph Tutorial",
        "Spark vs Hadoop",
        "Vector Databases",
        "RAG Best Practices",
    ]

    for example in examples:
        st.caption(f"• {example}")

    st.divider()

    # st.markdown("### 🤖 Workflow")

    # st.markdown("""
    #     ✅ Router  ->  🔍 Researcher  ->      
    #     📝 Planner  ->  👨‍💻 Writers  ->       
    #     📄 Final Blog
    #     """)

st.markdown("""
<div class="hero">

<h1 style="margin-bottom:8px;">
🤖 Agentic AI Blog Generator
</h1>

<h4 style="font-weight:400;color:#e5e7eb;margin-top:0;">
Generate production-ready technical blogs using
<b>LangGraph</b>,
<b>Gemini</b>,
and an
<b>Agentic AI Workflow</b>.
</h4>

<br>

<div style="display:flex;gap:12px;flex-wrap:wrap;">

<span style="
background:#ffffff22;
padding:8px 14px;
border-radius:25px;
">
⚡ LangGraph
</span>

<span style="
background:#ffffff22;
padding:8px 14px;
border-radius:25px;
">
🧠 Gemini LLM
</span>

<span style="
background:#ffffff22;
padding:8px 14px;
border-radius:25px;
">
📑 Markdown Export
</span>

<span style="
background:#ffffff22;
padding:8px 14px;
border-radius:25px;
">
🚀 Tavily Researcher
</span>

</div>

</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.subheader("✨ Features")

left,right = st.columns(2,gap="large")

with left:

    with st.container(border=True):

        st.markdown("## ⚡ Multi-Node Pipeline")

        st.write(
            """
Uses **LangGraph** to coordinate multiple agent nodes in a structured workflow.
Generate structured technical blogs through pipeline.
"""
        )

    st.write("")

    with st.container(border=True):

        st.markdown("## 📄 Markdown Export")

        st.write(
            """
Download blogs instantly in clean Markdown.

Perfect for:
- GitHub
- Dev.to
- Medium
- Documentation
"""
        )

with right:

    with st.container(border=True):

        st.markdown("## 🔍 Smart Research")

        st.write(
            """
The system automatically determines
whether web research is required.

It gathers relevant evidence using Tavily tool before
writing the blog.
"""
        )

    st.write("")

    with st.container(border=True):

        st.markdown("## 🚀 Production Ready")

        st.write(
            """
Built using:
- Gemini
- LangGraph
- Parallel Workflows
- Tavily Tool


Designed for high-quality technical writing.
""")
        
if generate:
    if not topic.strip():
        st.warning("Please enter a topic.")
    else:
        try:
            with st.spinner("Generating blog..."):
                st.session_state.blog=generate_blog(topic)
            st.success("Blog generated successfully!")
        except Exception as e:
            st.error(f"Generation failed: {e}")

if st.session_state.blog:
    blog = st.session_state.blog
    words = len(blog.split())
    mins = max(1, words // 200)

    st.markdown("---")

    with st.container(border=True):
        st.subheader("🤖 Agentic Workflow")
        st.markdown("✅ Router ➜ 🔍 Research ➜ 📝 Planner ➜ 👨‍💻 Writers ➜ 📄 Reducer")

    st.write("")

    c1,c2,c3=st.columns(3)
    c1.metric("📝 Words",words)
    c2.metric("⏱ Avg. Reading Time",f"{mins} min")
    c3.metric("Status","✅ Completed")

    st.write("")

    with st.container(border=True):

        st.subheader("📚 Generated Blog")

        preview,md=st.tabs(["📖 Preview","📝 Markdown"])

        with preview:
            st.markdown(blog)

        with md:
            st.code(blog,language="markdown")

    st.write("")

    d1,d2,d3=st.columns(3)

    with d1:
        st.download_button(
            "⬇ Download Markdown",
            blog,
            file_name="generated_blog.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with d2:
        st.download_button(
            "📄 Download TXT",
            blog,
            file_name="generated_blog.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with d3:
        if st.button("🔄 Generate Again",use_container_width=True):
            st.rerun()

else:
    st.info("Enter a topic and click Generate Blog.")

st.markdown('<div class="footer">Built with Streamlit • LangGraph • Gemini</div>',unsafe_allow_html=True)
