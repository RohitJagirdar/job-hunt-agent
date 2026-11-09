from app.schemas import JobCreate


MOCK_LISTINGS = [
    {
        "role_title": "Frontend Engineer",
        "company": "Razorpay",
        "region": "India",
        "location": "Bengaluru, India",
        "match_score": 91,
        "hiring_manager_hints": "Look for engineering managers in the Payments or Dashboard teams on LinkedIn.",
        "outreach_pitch": "Hi! I’m a frontend engineer who enjoys building fast, accessible product experiences. Razorpay’s work simplifying payments at scale is exciting, and I’d love to share how my React experience could support your team.",
        "description": "Build reliable React interfaces for merchants and internal teams. Collaborate with product and design, improve performance, and contribute to frontend architecture.",
        "source_url": "https://razorpay.com/jobs/",
    },
    {
        "role_title": "Software Engineer, Backend",
        "company": "Mercari",
        "region": "Japan",
        "location": "Tokyo, Japan",
        "match_score": 84,
        "hiring_manager_hints": "Search for backend platform leads and engineering managers at Mercari Japan.",
        "outreach_pitch": "Hello! I’m interested in Mercari’s marketplace platform and the engineering challenges behind trusted recommerce. My experience building API-driven services would let me contribute while learning from your team.",
        "description": "Design and operate backend services for a high-traffic marketplace. Work with Go or Kotlin, cloud infrastructure, and cross-functional teams in Tokyo.",
        "source_url": "https://careers.mercari.com/",
    },
    {
        "role_title": "Full Stack Engineer",
        "company": "Grab",
        "region": "Singapore",
        "location": "Singapore",
        "match_score": 88,
        "hiring_manager_hints": "Connect with engineering leads in the consumer platform or mobility organization.",
        "outreach_pitch": "Hi! I’m drawn to Grab’s work building products used across Southeast Asia. I’d be glad to bring my full-stack experience and a product-minded approach to a team solving meaningful everyday problems.",
        "description": "Develop customer-facing features across web and backend services. Partner with product, design, and data teams to ship dependable experiences.",
        "source_url": "https://www.grab.careers/",
    },
    {
        "role_title": "Product Engineer",
        "company": "Atlassian",
        "region": "India",
        "location": "Bengaluru, India",
        "match_score": 79,
        "hiring_manager_hints": "Identify team leads working on Jira, developer experience, or collaboration tools.",
        "outreach_pitch": "Hello! I’m motivated by tools that help teams do their best work. I’d love to bring my product engineering experience to Atlassian and help make collaboration simpler for customers.",
        "description": "Build and maintain product features for collaboration software. Use modern web technologies, write maintainable tests, and work in an agile team.",
        "source_url": "https://www.atlassian.com/company/careers",
    },
    {
        "role_title": "Software Engineer, Platform",
        "company": "SmartNews",
        "region": "Japan",
        "location": "Tokyo, Japan",
        "match_score": 76,
        "hiring_manager_hints": "Look for platform engineering managers and reliability leads based in Tokyo.",
        "outreach_pitch": "Hi! SmartNews’ mission to deliver quality information at scale is compelling. I’d love to discuss how my software engineering background could help build reliable systems for your readers.",
        "description": "Improve scalable platform services for a global news product. Collaborate across teams and contribute to service reliability, observability, and backend development.",
        "source_url": "https://about.smartnews.com/en/careers/",
    },
    {
        "role_title": "Frontend Developer",
        "company": "Carousell",
        "region": "Singapore",
        "location": "Singapore",
        "match_score": 82,
        "hiring_manager_hints": "Search for product engineering managers and frontend leads at Carousell.",
        "outreach_pitch": "Hello! I’m excited by Carousell’s circular-economy mission and its consumer product scale. I’d love to contribute my frontend skills to make discovery and selling even more seamless.",
        "description": "Create polished, accessible interfaces for a large consumer marketplace. Work closely with product and design and improve web performance.",
        "source_url": "https://careers.carousell.com/",
    },
]


def get_sample_listings() -> list[JobCreate]:
    return [JobCreate(**listing) for listing in MOCK_LISTINGS]
