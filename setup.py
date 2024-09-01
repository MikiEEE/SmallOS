from setuptools import setup, find_packages

setup(
    name="SmallOS",  
    version="1.0.2",  # Version of your package
    packages=find_packages(),  # Automatically find packages in the directory
    install_requires=[  # SmallOS should only use standard library
    ],
    author="Michael E",
    author_email="mikemp1997@gmail.com",
    description="Concurrent and Priority oriented Task Management System",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/MikiEEE/SmallOS",  # URL to your project
    classifiers=[  # Additional classifiers to specify metadata
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",  # Specify Python version requirement
)
