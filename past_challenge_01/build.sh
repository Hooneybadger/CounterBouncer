#!/bin/bash

# Exit immediately if any command fails.
set -e

# --- 1. Configuration (The "Recipe") ---
# This section defines all the settings for our build.

# Compiler
CXX="g++"

# Source files to be compiled
SOURCES="function.cpp myalgorithm.cpp"

# Name of the final output library
OUTPUT_LIB="lib_myalgorithm.so"

echo "--- Starting build process for ${OUTPUT_LIB} ---"

# Check for the GUROBI_HOME environment variable
if [ -z "$GUROBI_HOME" ]; then
    echo "Error: GUROBI_HOME is not set."
    echo "Please set it before running, e.g., export GUROBI_HOME=/opt/gurobi1200/linux64"
    exit 1
fi

# Compiler flags:
# -std=c++17 -> Use the C++17 standard
# -O3        -> High level of optimization for a release build
# -fPIC      -> Generate Position-Independent Code (REQUIRED for shared libraries)
CXXFLAGS="-std=c++17 -O3 -fPIC"

# Include directories:
# -I tells the compiler where to find header files (.hpp)
INCLUDE_DIRS="-I${GUROBI_HOME}/include"

# Linker flags:
# -shared -> Create a shared library (.so) instead of an executable
LDFLAGS="-shared"

# Library search paths:
# -L tells the linker where to find library files (.so, .a)
LIB_DIRS="-L${GUROBI_HOME}/lib"

# Libraries to link against:
# -l tells the linker which specific libraries to use
LIBS="-lgurobi_c++ -lgurobi120"


# --- 2. Compilation ---
# In this step, we compile each .cpp file into an intermediate "object file" (.o).

echo "--- Compiling source files into object files... ---"

# Loop through each source file and compile it
for source_file in ${SOURCES}; do
    echo "Compiling ${source_file}..."
    ${CXX} ${CXXFLAGS} ${INCLUDE_DIRS} -c ${source_file} -o ${source_file%.cpp}.o
done


# --- 3. Linking ---
# In this step, we take all the object files and "link" them together with the Gurobi
# libraries to create the final myAlgorithm.so file.

echo ""
echo "--- Linking object files into a shared library... ---"

# Create a list of all our object files
OBJECTS=$(for s in ${SOURCES}; do echo "${s%.cpp}.o"; done)

# The final link command
# ${CXX} ${LDFLAGS} -o ${OUTPUT_LIB} ${OBJECTS} ${LIB_DIRS} ${LIBS}
${CXX} ${LDFLAGS} -Wl,-soname,${OUTPUT_LIB} -o ${OUTPUT_LIB} ${OBJECTS} ${LIB_DIRS} ${LIBS}



# --- 4. Cleanup ---
# The object files are no longer needed after linking.

echo ""
echo "--- Cleaning up intermediate object files... ---"
rm ${OBJECTS}


echo ""
echo "--- Build complete! ---"
echo "Shared library created: ${OUTPUT_LIB}"