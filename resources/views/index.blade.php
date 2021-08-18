<x-app>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 leading-tight">
            {{ __('LibreNMS MIB database') }}
        </h2>
    </x-slot>


<div class="shadow overflow-hidden border-b border-gray-200 sm:rounded-lg">
<table class="min-w-full divide-y divide-gray-200 bg-white">
    <thead class="bg-gray-100">
    <tr class="text-left text-gray-500 uppercase tracking-wider">
        <th scope="col" class="px-6 py-1 text-xs font-medium">OID</th>
        <th scope="col" class="py-1 text-xs font-medium">MIB</th>
    </tr>
    </thead>
    <tbody>
        @foreach($mibs as $oid => $name)
            <tr class="even:bg-gray-100">
                <td class="px-6"><a href="{{ route('mib', $name[0]) }}">{{ $oid }}</a></td>
                <td><a href="{{ route('mib', $name[0]) }}">{{ $name[0] }}</a></td>
            </tr>
        @endforeach
    </tbody>
</table>
</div>


</x-app>
