from rest_framework import serializers

from .common import CommonResponseSerializer

class ArtifactCompiler(serializers.Serializer):
    name = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)

class ArtifactType(serializers.Serializer):
    name = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)

class ArtifactAbi(serializers.Serializer):
    name = serializers.CharField()
    inputs = ArtifactType(many=True, read_only=True)

class Artifact(serializers.Serializer):
    contractName = serializers.CharField(read_only=True)
    constructorInputs = ArtifactType(many=True, read_only=True)
    abi = ArtifactAbi(many=True, read_only=True)
    bytecode = serializers.CharField(read_only=True)
    compiler = ArtifactCompiler(read_only=True)
    updatedAt = serializers.DateTimeField(read_only=True)

class ArtifactResponse(CommonResponseSerializer):
    success = serializers.BooleanField(read_only=True)
    artifact = Artifact(read_only=True)
