// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: Apache-2.0

#include <pxr/base/vt/array.h>
#include <pxr/base/gf/vec3f.h>
#include <pxr/usd/sdf/path.h>
#include <pxr/usd/usd/stage.h>
#include <pxr/usd/usdGeom/mesh.h>

#include <iostream>

PXR_NAMESPACE_USING_DIRECTIVE

int main()
{
  const char *path = "/tmp/openusd-core-smoke.usda";
  UsdStageRefPtr written = UsdStage::CreateNew(path);
  if (!written) {
    std::cerr << "create failed\n";
    return 10;
  }

  UsdGeomMesh mesh = UsdGeomMesh::Define(written, SdfPath("/Triangle"));
  mesh.CreatePointsAttr().Set(VtArray<GfVec3f>{
      GfVec3f(0.0f, 0.0f, 0.0f),
      GfVec3f(1.0f, 0.0f, 0.0f),
      GfVec3f(0.0f, 1.0f, 0.0f),
  });
  mesh.CreateFaceVertexCountsAttr().Set(VtArray<int>{3});
  mesh.CreateFaceVertexIndicesAttr().Set(VtArray<int>{0, 1, 2});
  if (!written->GetRootLayer()->Save()) {
    std::cerr << "save failed\n";
    return 11;
  }
  written.Reset();

  UsdStageRefPtr reopened = UsdStage::Open(path);
  if (!reopened) {
    std::cerr << "reopen failed\n";
    return 12;
  }
  UsdGeomMesh roundtrip(reopened->GetPrimAtPath(SdfPath("/Triangle")));
  VtArray<GfVec3f> points;
  VtArray<int> counts;
  VtArray<int> indices;
  if (!roundtrip || !roundtrip.GetPointsAttr().Get(&points) ||
      !roundtrip.GetFaceVertexCountsAttr().Get(&counts) ||
      !roundtrip.GetFaceVertexIndicesAttr().Get(&indices) || points.size() != 3 ||
      counts.size() != 1 || counts[0] != 3 || indices.size() != 3 || indices[0] != 0 ||
      indices[1] != 1 || indices[2] != 2)
  {
    std::cerr << "round-trip value mismatch\n";
    return 13;
  }

  std::cout << "USD_CORE_SMOKE_OK format=usda prim=/Triangle points=" << points.size() << "\n";
  return 0;
}
