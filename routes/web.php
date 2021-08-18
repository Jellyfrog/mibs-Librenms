<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\MibController;

/*
|--------------------------------------------------------------------------
| Web Routes
|--------------------------------------------------------------------------
|
| Here is where you can register web routes for your application. These
| routes are loaded by the RouteServiceProvider within a group which
| contains the "web" middleware group. Now create something great!
|
*/

Route::get('/', [MibController::class, 'index'])->name('index');
Route::get('/{mib}', [MibController::class, 'mib'])->name('mib');
