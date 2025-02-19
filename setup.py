from setuptools import setup, find_packages

setup(
    name="dStats",
    version="1.0.1",
    packages=find_packages(),
    include_package_data=True,
    description="A real-time web-based monitoring tool that provides performance stats for Docker containers and visualizes their network connectivity graph",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Abdullah Al Arif",
    author_email="arifcse21@gmail.com",
    url="https://github.com/Arifcse21/dStats",
    install_requires=[
        "Django>=5.1.5",
        "graphviz>=0.20.3",
        "daphne>=4.1.2",
        "requests>=2.32.3",
        "black>=24.10.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.12.3",
    entry_points={
        "console_scripts": [
            "dStats.server=dStats.server:main",
        ],
    },
)
